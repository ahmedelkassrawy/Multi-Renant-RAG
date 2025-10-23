from llama_index.core import StorageContext, VectorStoreIndex, get_response_synthesizer, Settings
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.vector_stores import MetadataFilters, MetadataFilter, FilterOperator
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.cohere import CohereEmbedding
from llama_index.llms.google_genai import GoogleGenAI
from sqlalchemy import make_url
import glob
from llama_index.core import SimpleDirectoryReader
import asyncpg
import os
import sys
import logging
import asyncio
from typing import List, Tuple, Dict, Optional

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, project_root)

from config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

class RAGService:
    def __init__(self,user_id:str,org_name:str,
                 chunk_size: int = 500, chunk_overlap:int = 10,
                 db_name:str = "rag_db"):
        self.settings = get_settings()
        self.user_id = user_id
        self.org_name = org_name
        self.chunk_size = chunk_size 
        self.chunk_overlap = chunk_overlap
        self.db_url = settings.DATABASE_URL
        self.db_name = db_name
        self.documents = []
        self.index = None

        self.llm = GoogleGenAI( 
            model="models/gemini-2.0-flash",
            api_key=self.settings.GOOGLE_API_KEY,
        )
        Settings.llm = self.llm
        
        self.embed_model = CohereEmbedding(
            api_key= self.settings.COHERE_API_KEY,
            model_name="embed-english-v3.0",
            input_type="search_document",  
        )
        Settings.embed_model = self.embed_model

        self.text_splitter = SentenceSplitter(
            chunk_size = self.chunk_size,
            chunk_overlap = self.chunk_overlap
        )

        self.url = make_url(self.db_url)
        self.conn_string = f"host={self.url.host} port={self.url.port} user={self.url.username} password={self.url.password} dbname={self.url.database}"

    async def check_files_availability(self, doc_path: str) -> bool:
        """Check if there are files in the folder"""
        loop = asyncio.get_event_loop()
        
        files_in_data = await loop.run_in_executor(
            None,
            lambda: glob.glob(os.path.join(doc_path, "*.*"))
        )

        if files_in_data:
            self.documents = await loop.run_in_executor(
                None,
                lambda: SimpleDirectoryReader(doc_path).load_data()
            )
            
            for doc in self.documents:
                doc.metadata["user_id"] = self.user_id
                doc.metadata["organization"] = self.org_name
        else:
            self.documents = []
            logger.error(f"No files found in {doc_path}")
            return False
        
        return True

    async def setup_db(self):
        """Setup of db"""
        conn = await asyncpg.connect(
            host=self.url.host,
            port=self.url.port,
            user=self.url.username,
            password=self.url.password,
            database='postgres'  
        )

        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", 
                self.db_name
            )

            if not exists:
                await conn.execute(f'CREATE DATABASE {self.db_name}')
                logger.info(f"Database '{self.db_name}' created successfully")
            else:
                logger.info(f"Database '{self.db_name}' already exists")
        finally:
            await conn.close()

    async def filtering_documents(self) -> Tuple[List, int]:
        """Check if all files are embedded or not to avoid re-embedding"""
        conn = await asyncpg.connect(
            host=self.url.host,
            port=self.url.port,
            user=self.url.username,
            password=self.url.password,
            database=self.url.database
        )

        try:
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'data_vector_store'
                )
            """)

            if not table_exists:
                logger.info("Vector store doesn't exist yet, will process all documents")
                return self.documents, 0
            
            base_query = """
                SELECT DISTINCT metadata_->>'file_path', metadata_->>'file_name',
                    metadata_->>'last_modified_date', metadata_->>'file_size'
                FROM data_vector_store
                WHERE metadata_->>'file_path' IS NOT NULL
            """

            query_params = []
            param_count = 1

            if self.user_id:
                base_query += f" AND metadata_->>'user_id' = ${param_count}"
                query_params.append(self.user_id)
                param_count += 1
                
            if self.org_name:
                base_query += f" AND metadata_->>'organization' = ${param_count}"
                query_params.append(self.org_name)
                param_count += 1

            rows = await conn.fetch(base_query, *query_params)

            embedded_files = {}
            for row in rows:
                file_path = row['file_path']
                if file_path:
                    embedded_files[file_path] = {
                        'file_name': row['file_name'],
                        'last_modified_date': row['last_modified_date'],
                        'file_size': int(row['file_size']) if row['file_size'] else 0
                    }
        finally:
            await conn.close()

        new_docs = []
        skipped_cnt = 0

        for doc in self.documents:
            file_path = doc.metadata.get("file_path")
            file_size = doc.metadata.get("file_size")
            last_modified = doc.metadata.get("last_modified_date")

            if file_path in embedded_files:
                existing = embedded_files[file_path]

                if (existing["file_size"] == file_size and
                    existing["last_modified_date"] == last_modified):
                    skipped_cnt += 1
                    continue

            new_docs.append(doc)

        return new_docs, skipped_cnt
    
    async def setup_vector_store(self, documents_to_process: List):
        """Setup vector store and create query engine"""
        loop = asyncio.get_event_loop()
        
        # Run vector store setup in executor (blocking operation)
        vector_store = await loop.run_in_executor(
            None,
            lambda: PGVectorStore.from_params(
                database=self.db_name,
                host=self.url.host,
                password=self.url.password,
                port=self.url.port,
                user=self.url.username,
                table_name="vector_store",
                embed_dim=1024,
                hybrid_search=True
            )
        )

        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        if documents_to_process:
            logger.info(f"\nEmbedding {len(documents_to_process)} new/modified documents...")

            self.index = await loop.run_in_executor(
                None,
                lambda: VectorStoreIndex.from_documents(
                    documents_to_process,
                    storage_context=storage_context,
                    transformations=[self.text_splitter],
                    show_progress=True
                )
            )
        else:
            logger.info("No new documents to embed. Loading existing index...")
            self.index = await loop.run_in_executor(
                None,
                lambda: VectorStoreIndex.from_vector_store(
                    vector_store=vector_store,
                    storage_context=storage_context,
                )
            )

        metadata_filters = MetadataFilters(
            filters=[
                MetadataFilter(
                    key="organization",
                    value=self.org_name,
                    operator=FilterOperator.EQ
                ),
            ]
        )

        retriever = VectorIndexRetriever(
            index=self.index,
            similarity_top_k=5,
            hybrid_top_k=3,
            filters=metadata_filters
        )
        response_synthesizer = get_response_synthesizer()

        query_engine = RetrieverQueryEngine(
            retriever=retriever,
            response_synthesizer=response_synthesizer,
        )

        return query_engine

    async def return_index(self, documents_to_process: List):
        """Return index after processing documents"""
        loop = asyncio.get_event_loop()
        
        vector_store = await loop.run_in_executor(
            None,
            lambda: PGVectorStore.from_params(
                database=self.db_name,
                host=self.url.host,
                password=self.url.password,
                port=self.url.port,
                user=self.url.username,
                table_name="vector_store",
                embed_dim=1024,
                hybrid_search=True
            )
        )

        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        self.index = await loop.run_in_executor(
            None,
            lambda: VectorStoreIndex.from_documents(
                documents_to_process,
                storage_context=storage_context,
                transformations=[self.text_splitter],
                show_progress=True,
            )
        )
        return self.index
    
    async def run(self, query: str, query_engine):
        """Run a query against the query engine"""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            query_engine.query,
            query
        )
        return response