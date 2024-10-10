from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

DATABASE_URL = "mysql+mysqlconnector://root:password@localhost/e_store"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Product(Base):
    __tablename__ = 'products'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), index=True)
    description = Column(Text)
    price = Column(Float)
    quantity = Column(Integer)
    image_url = Column(String(255))
    timestamp = Column(DateTime, default=datetime.utcnow)
    location = Column(String(100))
    seller_name = Column(String(100))
    seller_email = Column(String(100))
    seller_phone = Column(String(15))
    
    cart_items = relationship("CartItem", back_populates="product")



class CartItem(Base):
    __tablename__ = 'cart_items'

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey('products.id'))  
    quantity = Column(Integer, default=1)  

    product = relationship("Product", back_populates="cart_items")  

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100))
    email = Column(String(100), unique=True)
    password = Column(String(100))  
    city = Column(String(100))
    phone = Column(String(20))

    Base.metadata.create_all(bind=engine)