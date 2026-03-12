# Multi-Tenant RAG (Retrieval-Augmented Generation) System

A FastAPI-based multi-tenant Retrieval-Augmented Generation (RAG) system that enables organizations to securely upload, store, and query documents using vector embeddings. Built with organization-level isolation, each tenant's data is completely segregated with user authentication and authorization.

## Features

- **Multi-Tenant Architecture**: Complete data isolation per organization with user-based access control
- **JWT Authentication**: Secure token-based authentication system
- **Vector Search**: Powered by PostgreSQL with pgvector extension
- **Advanced Embeddings**: Cohere embeddings for high-quality document representations
- **Smart Document Processing**: Automatic duplicate detection based on file metadata
- **Flexible LLM Integration**: Google Gemini integration for intelligent query responses
- **Async Operations**: Built on async/await for high performance
- **Organization Management**: Create, list, and delete organizations with isolated data stores

## 🏗️ Architecture

```
Multi-Renant-RAG/
├── src/
│   ├── backend/
│   │   ├── api.py              # FastAPI endpoints
│   │   ├── auth_router.py      # Authentication & authorization
│   │   ├── service.py          # RAG service implementation
│   │   └── main.py             # Development entry point
│   └── schemes/
│       ├── base.py             # SQLAlchemy base configuration
│       ├── models.py           # Pydantic models
│       ├── user.py             # User database model
│       └── orgs.py             # Organization database model
├── config.py                   # Application configuration
└── requirements_async.txt      # Python dependencies
```

## 📋 Prerequisites

- Python 3.8+
- PostgreSQL 14+ with pgvector extension
- API keys for:
  - Google Gemini AI
  - Cohere
  - Groq (optional)

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/ahmedelkassrawy/Multi-Renant-RAG.git
   cd Multi-Renant-RAG
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements_async.txt
   pip install fastapi uvicorn passlib[bcrypt] python-jose[cryptography] \
               llama-index llama-index-vector-stores-postgres \
               llama-index-embeddings-cohere llama-index-llms-google-genai
   ```

3. **Set up environment variables**
   
   Create a `.env` file in the project root:
   ```env
   # API Keys
   GOOGLE_API_KEY=your_google_api_key
   COHERE_API_KEY=your_cohere_api_key
   GROQ_API_KEY=your_groq_api_key

   # Database Configuration
   POSTGRES_USER=your_db_user
   POSTGRES_DB=your_db_name
   POSTGRES_PASSWORD=your_db_password
   DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/dbname
   ```

4. **Set up PostgreSQL with pgvector**
   ```bash
   # Install pgvector extension
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

## 🚀 Running the Application

**Start the server**
```bash
uvicorn src.backend.api:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

**Interactive API Documentation**
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 📚 API Endpoints

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Register a new user |
| POST | `/auth/login` | Login and receive JWT token |
| GET | `/auth/me` | Get current user information |
| POST | `/auth/create_tables` | Initialize database tables |

### Organizations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/me/organizations` | List all organizations for current user |
| POST | `/create_org` | Create a new organization |
| DELETE | `/delete_org` | Delete an organization and its data |

### Document Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/upload` | Upload and process documents |
| DELETE | `/delete_file` | Delete a specific file from vector store |
| POST | `/query` | Query documents using RAG |

## 💡 Usage Examples

### 1. Register a User
```bash
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username": "john_doe", "password": "secure_password"}'
```

### 2. Login
```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=john_doe&password=secure_password"
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### 3. Create an Organization
```bash
curl -X POST "http://localhost:8000/create_org" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"org_name": "my_company"}'
```

### 4. Upload Documents
```bash
curl -X POST "http://localhost:8000/upload" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "doc_path": "/path/to/document.pdf",
    "org_name": "my_company"
  }'
```

### 5. Query Documents
```bash
curl -X POST "http://localhost:8000/query" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the company policy on remote work?",
    "org_name": "my_company"
  }'
```

## 🔒 Security Features

- **JWT-based Authentication**: Secure token-based authentication with configurable expiration
- **Password Hashing**: Bcrypt password hashing for secure credential storage
- **Organization-level Isolation**: Each organization's data is completely isolated
- **User Authorization**: Users can only access their own organizations
- **Metadata Filtering**: Vector store queries are automatically filtered by user_id and organization

## 🎯 Key Components

### RAGService
The core service handling:
- Document embedding and storage
- Vector store management
- Query engine creation
- Duplicate document detection
- Organization-scoped data retrieval

### Authentication System
- User registration and login
- JWT token generation and validation
- Password hashing with bcrypt
- Current user dependency injection

### Vector Store
- PostgreSQL with pgvector extension
- Cohere embeddings (embed-english-v3.0)
- Metadata-based filtering for multi-tenancy
- Automatic table creation and management

## 🔧 Configuration

Edit `config.py` to customize:
- Database connections
- API key management
- Environment-specific settings

### RAG Parameters
Customize in `RAGService`:
- `chunk_size`: Document chunk size (default: 500)
- `chunk_overlap`: Overlap between chunks (default: 10)
- `db_name`: Vector store database name (default: "rag_db")

## 📊 Database Schema

### Users Table (`auth`)
- id (Primary Key)
- username (Unique)
- password (Hashed)
- organizations (JSON array)
- created_at

### Organizations Table (`orgs`)
- id (Primary Key)
- org_name
- user_id (Foreign Key)
- created_at

### Vector Store Table (`data_vector_store`)
- Automatically managed by pgvector
- Metadata includes: user_id, organization, file_name, file_path, etc.

## 🐛 Troubleshooting

**Database Connection Issues**
- Verify PostgreSQL is running
- Check DATABASE_URL format in `.env`
- Ensure pgvector extension is installed

**Authentication Errors**
- Verify JWT token is included in Authorization header
- Check token hasn't expired (30-minute default)
- Confirm SECRET_KEY is consistent

**Upload Failures**
- Verify file path exists and is accessible
- Check organization exists and user has access
- Ensure sufficient database storage

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

## 👤 Author

**Ahmed Elkassrawy**
- GitHub: [@ahmedelkassrawy](https://github.com/ahmedelkassrawy)

## 🙏 Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- Powered by [LlamaIndex](https://www.llamaindex.ai/)
- Vector search via [pgvector](https://github.com/pgvector/pgvector)
- Embeddings by [Cohere](https://cohere.com/)
- LLM by [Google Gemini](https://deepmind.google/technologies/gemini/)

---

⭐ Star this repository if you find it helpful!
