"""
Script to update admin user password in the database.
"""

from config.database import engine
from services.auth_service import AuthService
from sqlalchemy import text

# Hash the password using the project's native hashing function
hashed_password = AuthService.hash_password("admin12")
print(f"Password 'admin12' hashed successfully")
print(f"Hash: {hashed_password[:50]}...")

# Update the user directly with raw SQL
with engine.connect() as conn:
    # Update password and ensure user is active
    result = conn.execute(
        text("""
            UPDATE users
            SET password_hash = :password_hash,
                role = 'admin',
                is_active = true,
                full_name = 'Real Admin'
            WHERE email = :email
        """),
        {"password_hash": hashed_password, "email": "realadmin@test.com"}
    )
    conn.commit()

    if result.rowcount > 0:
        print(f"Successfully updated user: realadmin@test.com")
        print(f"  - Password updated: YES")
        print(f"  - Role: admin")
        print(f"  - Active: true")
    else:
        print(f"No user found with email: realadmin@test.com")

    # Verify the update
    verify_result = conn.execute(
        text("SELECT email, role, full_name, is_active FROM users WHERE email = :email"),
        {"email": "realadmin@test.com"}
    )
    user = verify_result.fetchone()
    if user:
        print(f"\nVerification:")
        print(f"  - Email: {user[0]}")
        print(f"  - Role: {user[1]}")
        print(f"  - Name: {user[2]}")
        print(f"  - Active: {user[3]}")

# Now test authentication using the AuthService
from config.database import SessionLocal

db = SessionLocal()
try:
    auth_service = AuthService(db)
    authenticated_user = auth_service.authenticate_user("realadmin@test.com", "admin12")
    print(f"\nAuthentication Test: PASSED")
    print(f"  - User: {authenticated_user.email}")
    print(f"  - Role: {authenticated_user.role.value}")
    print(f"  - Name: {authenticated_user.full_name}")
    print(f"\nLogin with 'realadmin@test.com' and 'admin12' is ready!")
except Exception as e:
    print(f"\nAuthentication Test: FAILED")
    print(f"  - Error: {str(e)}")
finally:
    db.close()
