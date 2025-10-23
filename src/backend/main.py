from llama_index.core import SimpleDirectoryReader
from llama_index.core import SimpleDirectoryReader, StorageContext
from llama_index.core import VectorStoreIndex
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.core.vector_stores import MetadataFilters, MetadataFilter, FilterOperator
import psycopg2
import textwrap
from sqlalchemy import make_url
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core import Settings
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.embeddings.cohere import CohereEmbedding
from llama_index.core import VectorStoreIndex, get_response_synthesizer, Settings
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, project_root)

from config import get_settings
import glob

settings = get_settings()
database_url = settings.DATABASE_URL 

llm = GoogleGenAI( 
    model="models/gemini-2.0-flash",
    api_key=settings.GOOGLE_API_KEY,
)

embed_model = CohereEmbedding(
    api_key=settings.COHERE_API_KEY,
    model_name="embed-english-v3.0",
    input_type="search_document",  
)

# === USER/ORGANIZATION CONFIGURATION ===
CURRENT_USER_ID = "kassra"  
CURRENT_ORGANIZATION = "kassra_org"  

doc_path = r"D:\Enviroment\rag\src\data"
files_in_data = glob.glob(os.path.join(doc_path, "*.*"))

if files_in_data:
    documents = SimpleDirectoryReader(doc_path).load_data()
    
    for doc in documents:
        doc.metadata['user_id'] = CURRENT_USER_ID
        doc.metadata['organization'] = CURRENT_ORGANIZATION
        
    print(f"Loaded {len(documents)} documents from {doc_path}")
    print(f"Tagged with user_id: {CURRENT_USER_ID}, organization: {CURRENT_ORGANIZATION}")
else:
    documents = []
    print(f"No files found in {doc_path}. Will load from existing vector store.")

text_splitter = SentenceSplitter(
    chunk_size = 512,
    chunk_overlap = 10
)

Settings.llm = llm
Settings.embed_model = embed_model
Settings.text_splitter = text_splitter

##DB
# Parse the database URL
url = make_url(database_url)
connection_string = f"host={url.host} port={url.port} user={url.username} password={url.password} dbname={url.database}"
db_name = "rag_db"

conn = psycopg2.connect(connection_string)
conn.autocommit = True

with conn.cursor() as c:
    c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
    exists = c.fetchone()

    if not exists:
        c.execute(f"CREATE DATABASE {db_name}")
        print(f"Database '{db_name}' created successfully.")
    else:
        print(f"Database '{db_name}' already exists.")

conn.close()

def get_embedded_files(db_name, url, user_id=None, organization=None):
    """Query the database to get all files that are already embedded for a user/org"""
    conn_str = f"host={url.host} port={url.port} user={url.username} password={url.password} dbname={db_name}"
    conn = psycopg2.connect(conn_str)
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'data_vector_store'
                )
            """)
            table_exists = cursor.fetchone()[0]
            
            if not table_exists:
                print("Vector store table doesn't exist yet. Will create and embed all documents.")
                return {}
            
            # Build query with optional user_id and organization filters
            base_query = """
                SELECT DISTINCT metadata_->>'file_path', metadata_->>'file_name', 
                       metadata_->>'last_modified_date', metadata_->>'file_size'
                FROM data_vector_store
                WHERE metadata_->>'file_path' IS NOT NULL
            """
            
            params = []

            if user_id:
                base_query += " AND metadata_->>'user_id' = %s"
                params.append(user_id)
            if organization:
                base_query += " AND metadata_->>'organization' = %s"
                params.append(organization)
            
            cursor.execute(base_query, params)
            
            embedded_files = {}
            for row in cursor.fetchall():
                file_path, file_name, last_modified, file_size = row
                if file_path:
                    embedded_files[file_path] = {
                        'file_name': file_name,
                        'last_modified_date': last_modified,
                        'file_size': int(file_size) if file_size else 0
                    }
            
            return embedded_files
    finally:
        conn.close()

def filter_new_documents(documents, embedded_files):
    """Filter out documents that are already embedded and unchanged"""
    new_documents = []
    skipped_count = 0
    
    for doc in documents:
        file_path = doc.metadata.get('file_path')
        file_size = doc.metadata.get('file_size')
        last_modified = doc.metadata.get('last_modified_date')
        
        if file_path in embedded_files:
            existing = embedded_files[file_path]
            if (existing['file_size'] == file_size and 
                existing['last_modified_date'] == last_modified):
                skipped_count += 1
                continue
        
        new_documents.append(doc)
    
    return new_documents, skipped_count

if documents:
    print("\nChecking for already embedded documents...")
    embedded_files = get_embedded_files(db_name, url, user_id=CURRENT_USER_ID, organization=CURRENT_ORGANIZATION)
    print(f"Found {len(embedded_files)} unique files already in database for this user/org")

    # Filter documents to only process new/modified ones
    documents_to_process, skipped = filter_new_documents(documents, embedded_files)
    print(f"Documents to embed: {len(documents_to_process)}")
    print(f"Documents skipped (already embedded): {skipped}")
else:
    documents_to_process = []
    print("\nNo local documents to check. Using existing vector store.")

vector_store = PGVectorStore.from_params(
    database = db_name,
    host = url.host,
    password = url.password,
    port = url.port,
    user = url.username,
    table_name = "vector_store",
    embed_dim = 1024 ,
    hybrid_search = True
)

storage_context = StorageContext.from_defaults(vector_store=vector_store)

if documents_to_process:
    print(f"\nEmbedding {len(documents_to_process)} new/modified documents...")
    index = VectorStoreIndex.from_documents(
        documents_to_process,
        storage_context=storage_context,
        transformations = [text_splitter],
        show_progress = True,
    )
else:
    print("\nNo new documents to embed. Loading existing index...")
    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        storage_context=storage_context,
    )

# === METADATA FILTERING FOR USER/ORGANIZATION ISOLATION ===
# Create filters to only retrieve documents for the current user's organization
metadata_filters = MetadataFilters(
    filters=[
        MetadataFilter(
            key="organization",
            value=CURRENT_ORGANIZATION,
            operator=FilterOperator.EQ
        ),
    ]
)

retriever = VectorIndexRetriever(
    index=index,
    similarity_top_k=5,
    hybrid_top_k=3,
    filters=metadata_filters
)
response_synthesizer = get_response_synthesizer()

query_engine = RetrieverQueryEngine(
    retriever = retriever,
    response_synthesizer = response_synthesizer,
)

query = input("User: ")
print(f"\n=== Query Context ===")
print(f"User ID: {CURRENT_USER_ID}")
print(f"Organization: {CURRENT_ORGANIZATION}")
print(f"Query: {query}")

response = query_engine.query(query)
print(f"\n=== Final Response ===")
print(f"RAG: {response}")