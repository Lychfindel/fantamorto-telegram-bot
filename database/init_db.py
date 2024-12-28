from models.db import Base, engine
import models.athlet  # Ensure all models are imported
import models.team
import models.game
import models.user
import models.bonus

# Create all tables in the database
Base.metadata.create_all(bind=engine)

print("Database tables created successfully!")