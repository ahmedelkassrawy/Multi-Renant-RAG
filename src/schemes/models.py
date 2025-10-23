from pydantic import BaseModel, Field
import os
from typing import Optional, List

class User(BaseModel):
    user_id: str
    username: str
    password: str
    organizations: Optional[List[str]] = None       

class Organizations(BaseModel):
    org_name: str
    user_id: str