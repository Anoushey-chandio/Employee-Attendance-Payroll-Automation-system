"""
Script to create/update admin user in the database.
"""

from config.database import SessionLocal
from models.user import User, UserRole
from services.auth_service import AuthService
from decimal import Decimal

# Create database session
db = SessionLocal()

try:
    # Hash the password using the project's native hashing function
    hashed_password = AuthService.hash_password("admin12")
    print(f"Password hashed successfully")

    # Check if user already exists
    existing_user = db.query(User).filter(User.email == "realadmin@test.com").first()

    if existing_user:
        # Update existing user
        existing_user.password_hash = hashed_password
        existing_user.role = UserRole.ADMIN
        existing_user.is_active = True
        db.commit()
        print(f"✓ Updated existing user: {existing_user.email}")
        print(f"  - Role: {existing_user.role.value}")
        print(f"  - Active: {existing_user.is_active}")
    else:
        # Create new admin user
        admin_user = User(
            email="realadmin@test.com",
            password_hash=hashed_password,
            full_name="Real Admin",
            role=UserRole.ADMIN,
            hourly_rate=Decimal("0.00"),
            is_active=True
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        print(f"✓ Created new admin user: {admin_user.email}")
        print(f"  - ID: {admin_user.id}")
        print(f"  - Role: {admin_user.role.value}")

    # Verify the user can be authenticated
    auth_service = AuthService(db)
    try:
        authenticated_user = auth_service.authenticate_user("realadmin@test.com", "admin12")
        print(f"\n✓ Authentication test PASSED")
        print(f"  - User: {authenticated_user.email}")
        print(f"  - Role: {authenticated_user.role.value}")
        print(f"  - Name: {authenticated_user.full_name}")
    except Exception as e:
        print(f"\n✗ Authentication test FAILED: {str(e)}")

except Exception as e:
    db.rollback()
    print(f"✗ Error: {str(e)}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
