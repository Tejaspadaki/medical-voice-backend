from typing import List, Optional, Any
from pydantic import BaseModel, ConfigDict

class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: Optional[List[str]] = []

class RoleCreate(RoleBase):
    pass

class RoleResponse(RoleBase):
    role_id: int
    
    model_config = ConfigDict(from_attributes=True)
