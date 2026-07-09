from src.main import create_app

app, _ = create_app()
with app.app_context():
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule.rule}")
