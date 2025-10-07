from django.test import Client
from django.contrib.auth import authenticate
from accounts.models import User
from django.urls import resolve
from django.conf import settings
import logging

# Enable detailed logging
logging.basicConfig(level=logging.DEBUG)

# ============================================================================
# SETUP: Get the LEARNER user
# ============================================================================

username = 'TC0120422'  # Replace with your test LEARNER username
password = 'TempPassword2024@123'  # Replace with password you set

print("="*80)
print("LEARNER LOGIN DIAGNOSTIC")
print("="*80)

# ============================================================================
# TEST 1: Verify User Exists and Has Correct Role
# ============================================================================

print("\n1. USER VERIFICATION")
print("-" * 80)

try:
    user = User.objects.get(username=username)
    print(f"✓ User found: {username}")
    print(f"  Email: {user.email}")
    print(f"  Is Active: {user.is_active}")
    print(f"  Is Staff: {user.is_staff}")
    print(f"  ACRP Role: '{user.acrp_role}'")
    print(f"  Role Type: {type(user.acrp_role)}")
    print(f"  Is LEARNER: {user.acrp_role == User.ACRPRole.LEARNER}")
    print(f"  ACRPRole.LEARNER value: '{User.ACRPRole.LEARNER}'")
except User.DoesNotExist:
    print(f"✗ User {username} NOT FOUND")
    print("Create user first before running this diagnostic")
    exit()

# ============================================================================
# TEST 2: Verify Authentication Works
# ============================================================================

print("\n2. AUTHENTICATION TEST")
print("-" * 80)

auth_user = authenticate(username=username, password=password)

if auth_user:
    print(f"✓ Authentication SUCCESSFUL")
    print(f"  Authenticated as: {auth_user.username}")
else:
    print(f"✗ Authentication FAILED")
    print(f"  Username/password don't match")
    print(f"  Fix password first: user.set_password('{password}'); user.save()")
    exit()

# ============================================================================
# TEST 3: Check LOGIN_REDIRECT_URL Setting
# ============================================================================

print("\n3. LOGIN REDIRECT CONFIGURATION")
print("-" * 80)

login_redirect = getattr(settings, 'LOGIN_REDIRECT_URL', '/')
print(f"LOGIN_REDIRECT_URL: '{login_redirect}'")

try:
    match = resolve(login_redirect)
    print(f"Redirect URL resolves to: {match.view_name}")
    print(f"View function: {match.func.__name__}")
except Exception as e:
    print(f"✗ Error resolving redirect URL: {e}")

# ============================================================================
# TEST 4: Simulate Complete Login Flow
# ============================================================================

print("\n4. SIMULATED LOGIN FLOW")
print("-" * 80)

client = Client()

# Step 1: Login
print("Step 1: Attempting login...")
login_response = client.login(username=username, password=password)

if not login_response:
    print("✗ Client.login() failed - authentication issue")
    exit()

print(f"✓ Client.login() succeeded")

# Step 2: Access root URL (what user sees after login)
print(f"\nStep 2: Accessing '{login_redirect}'...")
response = client.get(login_redirect, follow=False)

print(f"Response Status Code: {response.status_code}")
print(f"Response Status: {response.status_code} ({response.reason_phrase if hasattr(response, 'reason_phrase') else 'N/A'})")

if response.status_code == 200:
    print("✓ SUCCESS! User can access post-login page")
    
elif response.status_code == 302:
    print(f"↻ REDIRECT to: {response.url}")
    print(f"  This might be normal routing or a problem")
    
    # Follow the redirect
    print(f"\nStep 3: Following redirect...")
    response2 = client.get(response.url, follow=False)
    print(f"Final Status Code: {response2.status_code}")
    
    if response2.status_code == 302:
        print(f"↻ ANOTHER REDIRECT to: {response2.url}")
        if '/login' in response2.url or '/accounts/login' in response2.url:
            print("✗ PROBLEM: Redirecting back to login!")
            print("  This makes it LOOK like login failed")
            print("  But authentication actually succeeded")
            
elif response.status_code == 403:
    print("✗ FORBIDDEN (403)")
    print("  User authenticated but doesn't have permission")
    print("  This is the problem!")
    
elif response.status_code == 404:
    print("✗ NOT FOUND (404)")
    print("  Redirect URL doesn't exist")

# ============================================================================
# TEST 5: Access Dashboard Directly
# ============================================================================

print("\n5. DIRECT DASHBOARD ACCESS TEST")
print("-" * 80)

# Test /app/dashboard/ directly
dashboard_urls = ['/app/dashboard/', '/dashboard/', '/']

for url in dashboard_urls:
    try:
        response = client.get(url, follow=False)
        print(f"{url:20} → Status {response.status_code}")
        
        if response.status_code == 200:
            print(f"  ✓ Accessible")
        elif response.status_code == 302:
            print(f"  ↻ Redirects to: {response.url}")
        elif response.status_code == 403:
            print(f"  ✗ Forbidden (permission denied)")
        elif response.status_code == 404:
            print(f"  ✗ Not Found")
    except Exception as e:
        print(f"{url:20} → Error: {e}")

# ============================================================================
# TEST 6: Check User Permissions
# ============================================================================

print("\n6. USER PERMISSIONS CHECK")
print("-" * 80)

relevant_permissions = [
    'app.view_dashboard',
    'app.change_user',
    'accounts.view_user_list',
]

print("Checking relevant permissions:")
for perm in relevant_permissions:
    has_perm = user.has_perm(perm)
    print(f"  {perm:40} → {'✓ Yes' if has_perm else '✗ No'}")

all_perms = user.get_all_permissions()
print(f"\nTotal permissions: {len(all_perms)}")
if all_perms:
    print("All permissions:")
    for perm in sorted(all_perms):
        print(f"  - {perm}")
else:
    print("  ⚠️  User has NO permissions granted")

# ============================================================================
# TEST 7: Check User Groups
# ============================================================================

print("\n7. USER GROUPS CHECK")
print("-" * 80)

groups = user.groups.all()
print(f"User belongs to {groups.count()} group(s):")
for group in groups:
    print(f"  - {group.name}")
    group_perms = group.permissions.all()
    if group_perms:
        print(f"    Permissions from this group: {group_perms.count()}")

if not groups:
    print("  User belongs to NO groups")

# ============================================================================
# TEST 8: Compare with Working User (GLOBAL_SDP)
# ============================================================================

print("\n8. COMPARISON WITH WORKING USER")
print("-" * 80)

try:
    # Find a GLOBAL_SDP user for comparison
    working_user = User.objects.filter(acrp_role=User.ACRPRole.GLOBAL_SDP).first()
    
    if working_user:
        print(f"Comparing with: {working_user.username} (GLOBAL_SDP)")
        print(f"\n{'Attribute':<25} | {'LEARNER':<20} | {'GLOBAL_SDP':<20}")
        print("-" * 70)
        
        comparisons = [
            ('is_active', user.is_active, working_user.is_active),
            ('is_staff', user.is_staff, working_user.is_staff),
            ('is_superuser', user.is_superuser, working_user.is_superuser),
            ('permission_count', len(user.get_all_permissions()), len(working_user.get_all_permissions())),
            ('group_count', user.groups.count(), working_user.groups.count()),
        ]
        
        for attr, learner_val, sdp_val in comparisons:
            match = "✓" if learner_val == sdp_val else "✗"
            print(f"{attr:<25} | {str(learner_val):<20} | {str(sdp_val):<20} {match}")
        
        # Key differences
        print("\nKey Differences:")
        if user.is_staff != working_user.is_staff:
            print(f"  ⚠️  is_staff: LEARNER={user.is_staff}, SDP={working_user.is_staff}")
        
        learner_perms = set(user.get_all_permissions())
        sdp_perms = set(working_user.get_all_permissions())
        unique_to_sdp = sdp_perms - learner_perms
        
        if unique_to_sdp:
            print(f"  ⚠️  GLOBAL_SDP has {len(unique_to_sdp)} extra permissions:")
            for perm in sorted(list(unique_to_sdp)[:10]):  # Show first 10
                print(f"      - {perm}")
    else:
        print("No GLOBAL_SDP users found for comparison")
        
except Exception as e:
    print(f"Error during comparison: {e}")

# ============================================================================
# FINAL DIAGNOSIS
# ============================================================================

print("\n" + "="*80)
print("DIAGNOSIS SUMMARY")
print("="*80)

issues_found = []

if response.status_code == 302 and '/login' in response.url:
    issues_found.append("⚠️  CRITICAL: Redirect loop - user sent back to login after successful auth")
    issues_found.append("   FIX: Change LOGIN_REDIRECT_URL to '/app/dashboard/' in settings.py")

if response.status_code == 403:
    issues_found.append("⚠️  CRITICAL: Permission denied after login")
    issues_found.append("   FIX: Remove @permission_required from dashboard view OR grant permissions")

if user.acrp_role != User.ACRPRole.LEARNER:
    issues_found.append(f"⚠️  WARNING: User role is '{user.acrp_role}', expected 'LEARNER'")
    issues_found.append("   FIX: user.acrp_role = User.ACRPRole.LEARNER; user.save()")

if not user.is_active:
    issues_found.append("⚠️  CRITICAL: User account is inactive")
    issues_found.append("   FIX: user.is_active = True; user.save()")

if len(all_perms) == 0 and response.status_code == 403:
    issues_found.append("⚠️  WARNING: User has no permissions and got 403 error")
    issues_found.append("   FIX: Either grant permissions OR remove permission checks")

if issues_found:
    print("\nISSUES FOUND:")
    for issue in issues_found:
        print(issue)
else:
    print("\n✓ No obvious issues found")
    print("  Login should work properly")

print("\n" + "="*80)
print("END OF DIAGNOSTIC")
print("="*80)