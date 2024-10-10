from fastapi import FastAPI, Request, Depends, Form, Query, HTTPException, File, UploadFile
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from models import Product, CartItem, User, SessionLocal, engine, Base
from datetime import datetime
from typing import Optional
from starlette.middleware.sessions import SessionMiddleware

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key="key")

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_email = request.session.get("user_email")
    if not user_email:
        raise HTTPException(status_code=403, detail="Not authenticated")
    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        raise HTTPException(status_code=403, detail="User not found")
    return user

@app.get("/info")
def user_info(request: Request, db: Session = Depends(get_db)):
    try:
        user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse("/login")
    
    products = db.query(Product).filter(Product.seller_email == user.email).all()
    return templates.TemplateResponse("info.html", {"request": request, "user": user, "products": products})

@app.post("/product/remove/{product_id}")
def remove_product(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id, Product.seller_email == user.email).first()
    if product:
        db.delete(product)
        db.commit()
        return RedirectResponse("/info", status_code=302)
    raise HTTPException(status_code=404, detail="Product not found")

@app.get("/register")
def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
def register(
    request: Request, 
    full_name: str = Form(...), 
    email: str = Form(...), 
    password: str = Form(...), 
    city: str = Form(...), 
    phone: str = Form(...), 
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    if user:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Email already registered"
        })
    
    new_user = User(
        full_name=full_name,
        email=email,
        password=password,
        city=city,
        phone=phone
    )
    db.add(new_user)
    db.commit()
    
    return RedirectResponse("/login", status_code=302)

@app.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(
    request: Request, 
    email: str = Form(...), 
    password: str = Form(...), 
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email, User.password == password).first()
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid email or password"
        })
    
    request.session["user_email"] = user.email
    return RedirectResponse("/", status_code=302)

@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)

@app.get("/")
async def read_products(
    request: Request, 
    db: Session = Depends(get_db), 
    city: str = "", 
    search: str = "",
    min_price: Optional[str] = Query(default=None, description="Minimum price filter"),
    max_price: Optional[str] = Query(default=None, description="Maximum price filter")
):
    query = db.query(Product)

    if city:
        query = query.filter(Product.location == city)
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    if min_price:
        try:
            min_price_float = float(min_price)
            query = query.filter(Product.price >= min_price_float)
        except ValueError:
            raise HTTPException(status_code=400, detail="min_price must be a valid number")
    if max_price:
        try:
            max_price_float = float(max_price)
            query = query.filter(Product.price <= max_price_float)
        except ValueError:
            raise HTTPException(status_code=400, detail="max_price must be a valid number")
    
    products = query.order_by(Product.timestamp.desc()).all()
    for product in products:
        product.timestamp = product.timestamp.strftime("%d/%m %H:%M")

    return templates.TemplateResponse("index.html", {"request": request, "products": products})

@app.get("/add_item")
def add_item_form(request: Request, db: Session = Depends(get_db)):
    try:
        user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse("/login")
    
    return templates.TemplateResponse("add_item.html", {
        "request": request,
        "seller_name": user.full_name,
        "seller_email": user.email,
        "seller_phone": user.phone,
        "seller_city": user.city
    })

@app.post("/add_item")
async def add_item(
    name: str = Form(...), 
    description: str = Form(...), 
    price: float = Form(...), 
    quantity: int = Form(...),  
    location: str = Form(...), 
    image: UploadFile = File(...),  
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if not location:
        location = user.city

    image_path = f"static/images/{image.filename}"
    with open(image_path, "wb") as f:
        f.write(await image.read())

    new_product = Product(
        name=name, 
        description=description, 
        price=price, 
        quantity=quantity,  
        location=location,  
        seller_name=user.full_name,
        seller_email=user.email,
        seller_phone=user.phone,
        image_url=image_path
    )
    db.add(new_product)
    db.commit()
    return RedirectResponse("/", status_code=302)

@app.get("/cart")
def cart(request: Request, db: Session = Depends(get_db)):
    cart_items = db.query(CartItem).all()

    detailed_cart_items = []
    total_cost = 0.0
    for item in cart_items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
            item_cost = product.price * item.quantity
            total_cost += item_cost
            detailed_cart_items.append({
                "item": item, 
                "product": product, 
                "item_cost": item_cost, 
                "quantity": item.quantity
            })
    
    return templates.TemplateResponse("cart.html", {
        "request": request,
        "cart_items": detailed_cart_items,
        "total_cost": total_cost
    })

@app.post("/cart/add/{product_id}")
def add_to_cart(product_id: int, request: Request, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    existing_cart_item = db.query(CartItem).filter(CartItem.product_id == product_id).first()

    if existing_cart_item:
        if existing_cart_item.quantity < product.quantity:
            existing_cart_item.quantity += 1
            db.commit()
        referer = request.headers.get("referer", "/")
        return RedirectResponse(f"{referer}?added=true", status_code=302)

    if product.quantity > 0:
        cart_item = CartItem(product_id=product_id, quantity=1)
        db.add(cart_item)
        db.commit()

    referer = request.headers.get("referer", "/")
    return RedirectResponse(f"{referer}?added=true", status_code=302)

@app.post("/cart/remove/{item_id}")
def remove_from_cart(item_id: int, db: Session = Depends(get_db)):
    cart_item = db.query(CartItem).filter(CartItem.id == item_id).first()

    if cart_item:
        if cart_item.quantity > 1:
            cart_item.quantity -= 1
            db.commit()
        else:
            db.delete(cart_item)
            db.commit()
        return RedirectResponse("/cart", status_code=302)
    else:
        raise HTTPException(status_code=404, detail="Cart item not found")

@app.get("/product/{product_id}")
def product_detail(request: Request, product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        return templates.TemplateResponse("product.html", {"request": request, "product": product})
    raise HTTPException(status_code=404, detail="Product not found")

@app.post("/delete_account")
def delete_account(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.query(Product).filter(Product.seller_email == user.email).delete()
    db.delete(user)
    db.commit()
    request.session.clear()
    return RedirectResponse("/", status_code=302)
