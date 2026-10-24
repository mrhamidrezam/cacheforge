"""Example 4: Synchronous Decorators with Dynamic Key Builders and Invalidation."""

from cacheforge import cached

database = {
    1: {"name": "Alice", "role": "admin"},
    2: {"name": "Bob", "role": "developer"},
}

@cached(ttl=300)
def get_user_profile(user_id: int):
    print(f"  [DB Query] Fetching profile for user {user_id}...")
    return database.get(user_id)

def update_user_role(user_id: int, new_role: str):
    database[user_id]["role"] = new_role
    # Invalidate cache entry explicitly
    get_user_profile.invalidate(user_id)
    print(f"User {user_id} role updated to '{new_role}' and cache invalidated.")

def main():
    print("=== Initial Read (Cache Miss) ===")
    p1 = get_user_profile(1)
    print("Profile:", p1)

    print("\n=== Second Read (Cache Hit) ===")
    p2 = get_user_profile(1)
    print("Profile (from cache):", p2)

    print("\n=== Updating and Invalidating ===")
    update_user_role(1, "superadmin")

    print("\n=== Third Read (Refetched from DB) ===")
    p3 = get_user_profile(1)
    print("Profile (fresh):", p3)

    print("\nCache Stats:", get_user_profile.cache_info()["metrics"])

if __name__ == "__main__":
    main()
