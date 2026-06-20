"""Test script for authentication endpoints.

Usage:
  python scripts/test_auth_flow.py
  
This script demonstrates the complete auth flow:
  1. Signup
  2. Login
  3. Get current user
  4. Refresh token
  5. Logout
"""

import asyncio
import httpx
import sys
from datetime import datetime


BASE_URL = "http://localhost:8000"
TEST_EMAIL = f"test-{int(datetime.now().timestamp())}@example.com"
TEST_PASSWORD = "TestPass123"


async def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


async def test_signup() -> dict:
    """Test user signup."""
    await print_section("1. Testing Signup")
    
    payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
    }
    print(f"Request: POST {BASE_URL}/api/v1/auth/signup")
    print(f"Payload: {payload}")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{BASE_URL}/api/v1/auth/signup", json=payload)
    
    print(f"\nStatus: {response.status_code}")
    result = response.json()
    print(f"Response: {result}")
    
    if response.status_code != 201:
        print("❌ Signup failed!")
        return {}
    
    if result.get("success") and result.get("token"):
        print("✅ Signup successful!")
        return result.get("token")
    
    print("❌ Signup failed - no token!")
    return {}


async def test_login() -> dict:
    """Test user login."""
    await print_section("2. Testing Login")
    
    payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
    }
    print(f"Request: POST {BASE_URL}/api/v1/auth/login")
    print(f"Payload: {payload}")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{BASE_URL}/api/v1/auth/login", json=payload)
    
    print(f"\nStatus: {response.status_code}")
    result = response.json()
    print(f"Response: {result}")
    
    if response.status_code != 200:
        print("❌ Login failed!")
        return {}
    
    if result.get("success") and result.get("token"):
        print("✅ Login successful!")
        return result.get("token")
    
    print("❌ Login failed - no token!")
    return {}


async def test_get_current_user(access_token: str) -> bool:
    """Test getting current user info."""
    await print_section("3. Testing Get Current User")
    
    headers = {"Authorization": f"Bearer {access_token}"}
    print(f"Request: GET {BASE_URL}/api/v1/auth/me")
    print(f"Headers: Authorization: Bearer <token>")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{BASE_URL}/api/v1/auth/me", headers=headers)
    
    print(f"\nStatus: {response.status_code}")
    result = response.json()
    print(f"Response: {result}")
    
    if response.status_code == 200:
        print("✅ Get current user successful!")
        return True
    
    print("❌ Get current user failed!")
    return False


async def test_refresh_token(refresh_token: str) -> bool:
    """Test token refresh."""
    await print_section("4. Testing Token Refresh")
    
    headers = {"Authorization": f"Bearer {refresh_token}"}
    print(f"Request: POST {BASE_URL}/api/v1/auth/refresh")
    print(f"Headers: Authorization: Bearer <refresh_token>")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{BASE_URL}/api/v1/auth/refresh", headers=headers)
    
    print(f"\nStatus: {response.status_code}")
    result = response.json()
    print(f"Response: {result}")
    
    if response.status_code == 200:
        print("✅ Token refresh successful!")
        return True
    
    print("❌ Token refresh failed!")
    return False


async def test_logout(access_token: str) -> bool:
    """Test user logout."""
    await print_section("5. Testing Logout")
    
    headers = {"Authorization": f"Bearer {access_token}"}
    print(f"Request: POST {BASE_URL}/api/v1/auth/logout")
    print(f"Headers: Authorization: Bearer <token>")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{BASE_URL}/api/v1/auth/logout", headers=headers)
    
    print(f"\nStatus: {response.status_code}")
    result = response.json()
    print(f"Response: {result}")
    
    if response.status_code == 200:
        print("✅ Logout successful!")
        return True
    
    print("❌ Logout failed!")
    return False


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("  FinSight Authentication Test Suite")
    print("="*60)
    print(f"\nTest Email: {TEST_EMAIL}")
    print(f"Test Password: {TEST_PASSWORD}")
    print(f"Base URL: {BASE_URL}")
    
    try:
        # Test signup
        token1 = await test_signup()
        if not token1:
            print("\n❌ Auth flow terminated - signup failed")
            return 1
        
        # Test login
        token2 = await test_login()
        if not token2:
            print("\n❌ Auth flow terminated - login failed")
            return 1
        
        # Test get current user
        success = await test_get_current_user(token2.get("access_token", ""))
        if not success:
            print("\n⚠️  Warning: Get current user failed (continue)")
        
        # Test refresh token
        success = await test_refresh_token(token2.get("refresh_token", ""))
        if not success:
            print("\n⚠️  Warning: Token refresh failed (continue)")
        
        # Test logout
        success = await test_logout(token2.get("access_token", ""))
        if not success:
            print("\n⚠️  Warning: Logout may have failed")
        
        print("\n" + "="*60)
        print("  ✅ All tests completed!")
        print("="*60 + "\n")
        return 0
        
    except Exception as exc:
        print(f"\n❌ Error during testing: {exc}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
