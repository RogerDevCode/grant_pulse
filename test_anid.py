from src.infra.sources.catalog import iter_source_profiles, resolve_source_profile

for p in iter_source_profiles():
    print(f"Iter yielded key: {p.key}")

print("Resolve ANID_LLM:", resolve_source_profile("ANID_LLM").key)
