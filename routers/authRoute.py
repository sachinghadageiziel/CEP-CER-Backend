from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import requests
from typing import Optional

from db.database import SessionLocal
from db.models.user_model import User

router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"]
)

# Database Session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Request Models
class AccountInfo(BaseModel):
    name: str
    username: str
    localAccountId: str

class MicrosoftLoginRequest(BaseModel):
    accessToken: str
    account: AccountInfo

@router.get("/test")
async def test_route():
    """Test endpoint to verify route is working"""
    return {
        "status": "success",
        "message": "Auth route is working!",
        "timestamp": datetime.utcnow().isoformat()
    }

@router.post("/microsoft")
async def microsoft_login(
    request: MicrosoftLoginRequest,
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    """Authenticate user with Microsoft access token"""
    try:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Invalid authorization header")
        
        access_token = authorization.split("Bearer ")[1]
        
        if access_token != request.accessToken:
            raise HTTPException(status_code=401, detail="Token mismatch")
        
        print(f"🔍 Verifying token with Microsoft Graph API...")
        graph_response = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        
        if graph_response.status_code != 200:
            print(f"❌ Microsoft Graph API error: {graph_response.status_code}")
            raise HTTPException(
                status_code=401, 
                detail=f"Invalid access token: {graph_response.status_code}"
            )
        
        user_data = graph_response.json()
        print(f"✅ Microsoft Graph API response: {user_data}")
        
        email = user_data.get("mail") or user_data.get("userPrincipalName")
        name = user_data.get("displayName") or request.account.name
        microsoft_id = user_data.get("id") or request.account.localAccountId
        
        if not email:
            raise HTTPException(status_code=400, detail="Could not retrieve email from Microsoft")
        
        print(f"📧 User info - Email: {email}, Name: {name}, MS ID: {microsoft_id}")
        
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            print(f"✨ Creating new user...")
            new_user = User(
                email=email,
                name=name,
                microsoft_id=microsoft_id,
                role="user"
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            
            print(f"✅ New user registered: {name} ({email})")
            
            return {
                "status": "success",
                "message": "User registered successfully",
                "user": {
                    "id": new_user.id,
                    "email": new_user.email,
                    "name": new_user.name,
                    "microsoft_id": new_user.microsoft_id,
                    "role": new_user.role,
                    "is_new": True
                },
                "access_token": access_token
            }
        else:
            print(f"👤 Existing user logged in")
            
            if not user.microsoft_id:
                user.microsoft_id = microsoft_id
                db.commit()
            
            print(f"✅ User logged in: {name} ({email})")
            
            return {
                "status": "success",
                "message": "User logged in successfully",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "microsoft_id": user.microsoft_id,
                    "role": user.role,
                    "is_new": False
                },
                "access_token": access_token
            }
    
    except requests.RequestException as e:
        print(f"❌ Microsoft Graph API error: {e}")
        raise HTTPException(status_code=500, detail="Failed to verify Microsoft token")
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Authentication error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")

@router.get("/me")
async def get_current_user(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    """Get current authenticated user information"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    access_token = authorization.split("Bearer ")[1]
    
    try:
        graph_response = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        
        if graph_response.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_data = graph_response.json()
        email = user_data.get("mail") or user_data.get("userPrincipalName")
        
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found in database")
        
        return {
            "status": "success",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "microsoft_id": user.microsoft_id,
                "role": user.role,
            }
        }
    except requests.RequestException as e:
        print(f"❌ Error fetching user: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch user information")
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/logout")
async def logout():
    """Logout endpoint"""
    return {
        "status": "success",
        "message": "Logged out successfully"
    }