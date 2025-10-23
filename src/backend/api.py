from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text
import os
import sys
import asyncio
import asyncpg
from sqlalchemy import select

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, project_root)

from config import get_settings
from src.backend.service import RAGService
from llama_index.core import SimpleDirectoryReader
from sqlalchemy import make_url
import logging
from src.backend.auth_router import router as auth_router, get_current_user, get_async_db
from src.schemes.user import Auth
from src.schemes.orgs import Orgs

app = FastAPI(title="RAG API", version="1.0.0")

# Include authentication router
app.include_router(auth_router)

logger = logging.getLogger(__name__)
settings = get_settings()
db_url = settings.DATABASE_URL


async_db_url = db_url.replace("postgresql+psycopg://", "postgresql+asyncpg://")
async_engine = create_async_engine(async_db_url, echo=False)
AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

url = make_url(db_url)
conn_string = f"host={url.host} port={url.port} user={url.username} password={url.password} dbname={url.database}"


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

@app.get("/")
async def root():
    return {"message": "RAG API is running"}

@app.get("/me/organizations")
async def get_organization(
    current_user: Auth = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all organizations for the current user"""
    result = await db.execute(select(Orgs).filter(Orgs.user_id == current_user.id))
    user_orgs = result.scalars().all()
    
    if not user_orgs:
        return {"message": "No organizations found", 
                "organizations": []}
    
    return {
        "username": current_user.username,
        "organizations": 
        [
            {
                "id": org.id, 
                "org_name": org.org_name, 
                "created_at": org.created_at} 
                for org in user_orgs
        ]
    }
        
@app.post("/upload")
async def upload_files(
    doc_path: str,
    org_name: str,
    current_user: Auth = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload and process files for RAG"""

    result = await db.execute(
        select(Orgs).filter(
            Orgs.org_name == org_name,
            Orgs.user_id == current_user.id
        )
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(status_code=403, detail="You don't have access to this organization")
    
    service = RAGService(user_id = str(current_user.id), 
                         org_name = org_name)
    
    loop = asyncio.get_event_loop()
    docs = await loop.run_in_executor(
        None,
        lambda: SimpleDirectoryReader(input_files=[doc_path]).load_data()
    )
    
    for doc in docs:
        doc.metadata['user_id'] = str(current_user.id)
        doc.metadata['organization'] = org_name

    index = await service.return_index(docs)
    
    return {
        "message": "Files uploaded successfully",
        "processed": len(docs),
        "organization": org_name
    }
    
@app.delete("/delete_file")
async def delete_file(
    file_name: str,
    org_name: str,
    current_user: Auth = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a file from the vector store"""

    result = await db.execute(
        select(Orgs).filter(
            Orgs.org_name == org_name,
            Orgs.user_id == current_user.id
        )
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(status_code=403, detail="You don't have access to this organization")
    
    conn = await asyncpg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        database=url.database
    )

    try:
        query = """
                SELECT metadata_->>'file_name'
                FROM data_vector_store
                WHERE metadata_->>'file_name' = $1
                AND metadata_->>'organization' = $2
                AND metadata_->>'user_id' = $3
                """
        exists = await conn.fetchval(query, file_name, org_name, str(current_user.id))

        if exists:
            query = """
                    DELETE FROM data_vector_store 
                    WHERE metadata_->>'file_name' = $1
                    AND metadata_->>'organization' = $2
                    AND metadata_->>'user_id' = $3
                    """
            await conn.execute(query, file_name, org_name, str(current_user.id))
            
            logger.info(f"File: {file_name} has been successfully deleted")
            return {"message": f"File {file_name} deleted successfully"}
        else:
            logger.error(f"File: {file_name} doesn't exist")
            raise HTTPException(status_code=404, detail=f"File {file_name} not found")
    finally:
        await conn.close()

@app.post("/create_org")
async def create_org(
    org_name: str,
    current_user: Auth = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Orgs).filter(
        Orgs.org_name == org_name,
        Orgs.user_id == current_user.id
    ))
    existing_org = result.scalar_one_or_none()
    
    if existing_org:
        raise HTTPException(status_code=400, detail="Organization already exists for this user")
    
    new_org = Orgs(
        org_name=org_name,
        user_id=current_user.id
    )
    
    db.add(new_org)
    

    current_orgs = current_user.organizations or []

    if org_name not in current_orgs:
        current_orgs.append(org_name)
        current_user.organizations = current_orgs
    
    await db.commit()
    await db.refresh(new_org)
    
    return {
        "message": "Organization created successfully",
        "organization": {
            "id": new_org.id,
            "org_name": new_org.org_name,
            "created_at": new_org.created_at
        }
    }

@app.delete("/delete_org")
async def delete_org(
    org_name: str,
    current_user: Auth = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Orgs).filter(
        Orgs.org_name == org_name,
        Orgs.user_id == current_user.id
    ))
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    current_orgs = current_user.organizations or []

    if org_name in current_orgs:
        current_orgs.remove(org_name)
        current_user.organizations = current_orgs
    
    await db.delete(org)
    await db.commit()
    

    conn = await asyncpg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        database=url.database
    )
    try:
        query = """
                DELETE FROM data_vector_store 
                WHERE metadata_->>'organization' = $1
                AND metadata_->>'user_id' = $2
                """
        await conn.execute(query, org_name, str(current_user.id))
        logger.info(f"Deleted vector store data for organization: {org_name}")
    finally:
        await conn.close()
    
    return {"message": f"Organization {org_name} deleted successfully"}

@app.post("/query")
async def query_rag(
    query: str,
    org_name: str,
    current_user: Auth = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Orgs).filter(
        Orgs.org_name == org_name,
        Orgs.user_id == current_user.id
    ))
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(status_code=403, detail="You don't have access to this organization")
    
    service = RAGService(user_id=str(current_user.id), org_name=org_name)
    
    query_engine = await service.setup_vector_store([], 0)
    
    response = await service.run(query, query_engine)
    
    return {
        "query": query,
        "response": str(response),
        "organization": org_name
    }