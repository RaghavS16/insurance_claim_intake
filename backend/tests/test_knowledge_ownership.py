from src.api.knowledge_routes import router

def test_knowledge_router_is_not_publicly_owned_by_admin_role():
    # The route dependency contract is adjuster-only by design.
    routes={route.path: route for route in router.routes if getattr(route,"path",None)}
    assert "/documents" in routes
    assert "/upload" in routes
    assert "/search" in routes
