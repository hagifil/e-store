from fastapi import FastAPI, Request, Depends, Form, Query, HTTPException, File, UploadFile
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from models import Product, CartItem, User, SessionLocal, engine, Base
from datetime import datetime
from typing import Optional
from starlette.middleware.sessions import SessionMiddleware

# Create the database tables
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Set up session middleware
app.add_middleware(SessionMiddleware, secret_key="my_super_secret_key_12345")

# Mount static files (e.g., CSS and images)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# Dependency to get the DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# User authentication logic
def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_email = request.session.get("user_email")
    print("Current user email:", user_email)
    if not user_email:
        raise HTTPException(status_code=403, detail="Not authenticated")
    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        raise HTTPException(status_code=403, detail="User not found")
    return user

@app.get("/info")
def user_info(request: Request, db: Session = Depends(get_db)):
    try:
        user = get_current_user(request, db)  # Check for authenticated user
    except HTTPException:
        return RedirectResponse("/login")  # Redirect to login if not authenticated
    
    products = db.query(Product).filter(Product.seller_email == user.email).all()
    return templates.TemplateResponse("info.html", {"request": request, "user": user, "products": products})

# Remove product
@app.post("/product/remove/{product_id}")
def remove_product(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id, Product.seller_email == user.email).first()
    if product:
        db.delete(product)
        db.commit()
        return RedirectResponse("/info", status_code=302)
    raise HTTPException(status_code=404, detail="Product not found")

# User Registration Route
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
    # Check if the user already exists
    user = db.query(User).filter(User.email == email).first()
    if user:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Email already registered"
        })
    
    new_user = User(
        full_name=full_name,
        email=email,
        password=password,  # In production, make sure to hash the password
        city=city,
        phone=phone
    )
    db.add(new_user)
    db.commit()
    
    return RedirectResponse("/login", status_code=302)

# User Login Route
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
    
    # Store user email in session
    request.session["user_email"] = user.email  # Save the user's email in session
    print("Session set:", request.session)  # Debugging line

    return RedirectResponse("/", status_code=302)

# User Logout Route
@app.post("/logout")
def logout(request: Request):
    request.session.clear()  # Clear the session
    return RedirectResponse("/", status_code=302)

# Display products with optional filtering
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
        query = query.filter(Product.location == city)  # Filter by city if provided
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))  # Case-insensitive search
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
    
    products = query.order_by(Product.timestamp.desc()).all()  # Order by timestamp desc
    for product in products:
        product.timestamp = product.timestamp.strftime("%d/%m %H:%M")  # Format timestamp

    return templates.TemplateResponse("index.html", {"request": request, "products": products})

# Add new product form
@app.get("/add_item")
def add_item_form(request: Request, db: Session = Depends(get_db)):
    try:
        user = get_current_user(request, db)  # Check for authenticated user
    except HTTPException:
        return RedirectResponse("/login")  # Redirect to login if not authenticated
    
    return templates.TemplateResponse("add_item.html", {
        "request": request,
        "seller_name": user.full_name,
        "seller_email": user.email,
        "seller_phone": user.phone,
        "seller_city": user.city
    })

# Add new product submission
@app.post("/add_item")
async def add_item(
    name: str = Form(...), 
    description: str = Form(...), 
    price: float = Form(...), 
    quantity: int = Form(...),  
    location: str = Form(...),  # This will take the default value from the form
    image: UploadFile = File(...),  
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)  # Ensure user is logged in
):
    # Use the user's city as the location if it's not provided
    if not location:
        location = user.city  # Default to user's city if no location is given

    # Save the uploaded image to the server
    image_path = f"static/images/{image.filename}"
    with open(image_path, "wb") as f:
        f.write(await image.read())  # Save the uploaded image

    new_product = Product(
        name=name, 
        description=description, 
        price=price, 
        quantity=quantity,  
        location=location,  
        seller_name=user.full_name,  # Use user details
        seller_email=user.email,
        seller_phone=user.phone,  
        image_url=image_path  # Save the path to the uploaded image
    )
    db.add(new_product)
    db.commit()
    return RedirectResponse("/", status_code=302)

# Shopping Cart page
@app.get("/cart")
def cart(request: Request, db: Session = Depends(get_db)):
    cart_items = db.query(CartItem).all()

    detailed_cart_items = []
    total_cost = 0.0
    for item in cart_items:
        product = db.query(Product).filter(Product.id == item.product_id).first()  # Fetch product by ID
        if product:
            item_cost = product.price * item.quantity  # Calculate the cost for each cart item
            total_cost += item_cost  # Add to the total cost
            detailed_cart_items.append({
                "item": item, 
                "product": product, 
                "item_cost": item_cost, 
                "quantity": item.quantity  # Include the live quantity
            })
    
    return templates.TemplateResponse("cart.html", {
        "request": request,
        "cart_items": detailed_cart_items,
        "total_cost": total_cost
    })

# Add item to cart
@app.post("/cart/add/{product_id}")
def add_to_cart(product_id: int, request: Request, db: Session = Depends(get_db)):
    # Fetch the product from the database
    product = db.query(Product).filter(Product.id == product_id).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check if the product is already in the cart
    existing_cart_item = db.query(CartItem).filter(CartItem.product_id == product_id).first()

    if existing_cart_item:
        # If the product is already in the cart, increment the cart quantity if there's enough stock
        if existing_cart_item.quantity < product.quantity:
            existing_cart_item.quantity += 1
            db.commit()
        # Redirect back to the referring page with the "added" flag set
        referer = request.headers.get("referer", "/")
        return RedirectResponse(f"{referer}?added=true", status_code=302)

    # If the product is not in the cart and there's available stock, add it with an initial quantity of 1
    if product.quantity > 0:
        cart_item = CartItem(product_id=product_id, quantity=1)
        db.add(cart_item)
        db.commit()

    # Redirect back to the referring page with the "added" flag set
    referer = request.headers.get("referer", "/")
    return RedirectResponse(f"{referer}?added=true", status_code=302)

# Remove item from cart
@app.post("/cart/remove/{item_id}")
def remove_from_cart(item_id: int, db: Session = Depends(get_db)):
    # Find the cart item by its ID
    cart_item = db.query(CartItem).filter(CartItem.id == item_id).first()

    if cart_item:
        if cart_item.quantity > 1:
            cart_item.quantity -= 1  # Decrement the quantity by 1
            db.commit()  # Commit the changes
        else:
            db.delete(cart_item)  # Delete the item if the quantity is 1
            db.commit()  # Commit the changes
        return RedirectResponse("/cart", status_code=302)  # Redirect to the cart page
    else:
        raise HTTPException(status_code=404, detail="Cart item not found")

# Product details page
@app.get("/product/{product_id}")
def product_detail(request: Request, product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        return templates.TemplateResponse("product.html", {"request": request, "product": product})
    raise HTTPException(status_code=404, detail="Product not found")

@app.post("/delete_account")
def delete_account(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Delete the user's products
    db.query(Product).filter(Product.seller_email == user.email).delete()
    
    # Delete the user account
    db.delete(user)
    db.commit()
    
    # Clear session and redirect to home page after account deletion
    request.session.clear()  # Clear the session
    return RedirectResponse("/", status_code=302)

@app.post("/product/update_quantity/{product_id}")
async def update_product_quantity(
    product_id: int,
    new_quantity: int = Form(...),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return {"error": "Product not found"}
    
    product.quantity = new_quantity
    db.commit()
    return RedirectResponse("/info", status_code=302)