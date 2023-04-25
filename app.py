from flask import Flask, jsonify, request, json
import requests
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
from werkzeug.utils import secure_filename
import os
import re

app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:123456@localhost:3306/miniprogram'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 用户与图片收藏列表是n对n关系，定义一个中间表
user_image_collection = db.Table('user_image_collection',
                                 db.Column('user_id', db.String(16), db.ForeignKey('user.id'), primary_key=True),
                                 db.Column('image_id', db.Integer, db.ForeignKey('image.id'), primary_key=True),
                                 )


class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.String(16), primary_key=True)
    name = db.Column(db.String(50))
    openid = db.Column(db.String(128))
    collections = db.relationship('Image', secondary=user_image_collection, backref='users')
    orders = db.relationship('Order', backref='user')


class Image(db.Model):
    __tablename__ = 'image'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50))
    category = db.Column(db.String(16))
    src = db.Column(db.String(200))
    thumb = db.Column(db.String(200))
    is_collected = False # add a new attribute to each image indicating whether it is in the user's collections

class OrderDetail(db.Model):
    __tablename__ = 'order_detail'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    text = db.Column(db.String(200))
    image_path = db.Column(db.String(200))
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))

class Order(db.Model):
    __tablename__ = 'order'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50))
    status = db.Column(db.String(50))#已下单、已结束
    quantity = db.Column(db.Integer) #新增数量字段
    order_time = db.Column(db.DateTime) #新增下单时间字段
    category = db.Column(db.String(50)) #新增类别字段
    payment_status = db.Column(db.String(50)) #新增付款情况字段
    payment_amount = db.Column(db.Float) #新增付款金额字段
    details = db.relationship('OrderDetail', backref='order') #修改details字段为关联OrderDetail类
    user_id = db.Column(db.String(16), db.ForeignKey('user.id'))

#捏图人数、时间信息、付款金额、付款情况、图片分类、细节+图片，捏脸文件用QQ发送

#创建数据库表
# with app.app_context():
#     db.drop_all()
#     db.create_all()

@app.route('/get_user', methods=['POST'])
def get_user():
    data = request.json
    print(data)
    user_id = data['user_id']
    code = data['code']
    wx_response = requests.get(f'https://api.weixin.qq.com/sns/jscode2session?appid=wxf696fa0da2b7b059&secret=0c43d97d1f61b78ab2360bde54619857&js_code='+ code + '&grant_type=authorization_code')
    wx_server_res = wx_response.json()
    openid = wx_server_res['openid']
    print(openid)
    exist_user = User.query.filter_by(openid=openid).first()
    check_user = User.query.filter_by(id=user_id, openid=openid).first()
    if exist_user is None:
        user = User(id=user_id, name='用户'+user_id, openid = openid)
        db.session.add(user)
        db.session.commit()
        u_dict = {'user_id': exist_user.id, 'user_name': exist_user.name}
    elif check_user is None:
        u_dict = {'user_id': 400, 'user_name': '每个用户只能绑定一个手机号码'}
    else:
        u_dict = {'user_id': check_user.id, 'user_name': check_user.name}
    return jsonify(u_dict)

@app.route('/retrieve_user', methods=['POST'])
def retrieve_user():
    data = request.json
    print(data)
    code = data['code']
    wx_response = requests.get(f'https://api.weixin.qq.com/sns/jscode2session?appid=wxf696fa0da2b7b059&secret=0c43d97d1f61b78ab2360bde54619857&js_code='+ code + '&grant_type=authorization_code')
    wx_server_res = wx_response.json()
    openid = wx_server_res['openid']
    exist_user = User.query.filter_by(openid=openid).first()
    if exist_user is None :
        return jsonify({'user_id': 400, 'user_name': '暂未注册'})
    return jsonify({'user_id' : exist_user.id, 'user_name' : exist_user.name})

@app.route('/add_image', methods=['POST'])
def add_image():
    data = request.json
    name = data['name']
    src = data['src']
    thumb = data['thumb']
    category = data['category']
    image = Image(name=name, src=src, thumb=thumb, category=category)
    db.session.add(image)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/<category>/get_images')
def get_images(category):
    user_id = request.args.get('user_id')
    if user_id is None:
        images = Image.query.filter_by(category=category).all()
    else:
        user = User.query.get(user_id)
        if user is None:
            images = Image.query.filter_by(category=category).all()
        else:
            images = Image.query.filter_by(category=category).all()
            for img in images:
                img.is_collected = img.id in [i.id for i in user.collections]
    return jsonify([{'id' : i.id, 'name': i.name, 'thumb': i.thumb, 'src': i.src, 'is_collected': i.is_collected} for i in images])

@app.route('/order', methods=['POST'])
def place_order():
    data = request.json
    user_id = data['user_id']
    name = data['order_name']
    status = data['order_status']
    quantity = data['order_number']

    order_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ran_num = data['ran_num'].replace("(中国标准时间)", "")
    ran_num = re.sub(r'\W', '', ran_num)

    category = data['order_category']
    payment_status = data['payment_status']
    payment_amount = data['payment_amount']
    details = []
    for detail in data['detailRows']:
        text = detail['detail']
        image_path = os.getcwd()+ '\\orderdetail\\' + name + user_id + ran_num + "\\" + detail['imagePath'][11:]
        order_detail = OrderDetail(text=text, image_path=image_path)
        details.append(order_detail)
    order = Order(name=name, status=status, quantity=quantity, order_time=order_time, category=category, payment_status=payment_status, payment_amount=payment_amount, details=details, user_id=user_id)
    db.session.add(order)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/orderdetail/image', methods=['POST'])
def place_detail_image():
    name = request.form['order_name']

    ran_num = request.form['ran_num'].replace("(中国标准时间)","")
    ran_num = re.sub(r'\W','',ran_num)
    folder_name = request.form['user_id']+ran_num

    file = request.files['image']
    filename = secure_filename(file.filename)
    folder_path = os.path.join(os.getcwd()+'/orderdetail/', name+folder_name)
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    file.save(os.path.join(folder_path, filename))
    return jsonify({'success': True})

@app.route('/user/<user_id>/orders')
def get_user_orders(user_id):
    orders = Order.query.filter_by(user_id=user_id).all()
    if orders is None:
        return jsonify({'error': 'Order not found'})
    return jsonify([{'order_id' : o.id, 'name': o.name, 'status': o.status, 'order_category' : o.category,'quantity': o.quantity,
                  'order_time': o.order_time.strftime("%Y-%m-%d %H:%M:%S"), 'payment_status': o.payment_status,
                  'payment_amount': o.payment_amount} for o in orders])

@app.route('/user/<user_id>/orders/<order_id>')
def get_user_order(user_id, order_id):
    order = Order.query.filter_by(user_id=user_id, id=order_id).first()
    if order is None:
        return jsonify({'error': 'Order not found'})
    orders = Order.query.order_by(Order.order_time).all()
    number = orders.index(order) + 1
    order_dict = {'id': order.id, 'name': order.name, 'status': order.status, 'quantity': order.quantity,
                  'order_time': order.order_time.strftime("%Y-%m-%d %H:%M:%S"), 'payment_status': order.payment_status,
                  'payment_amount': order.payment_amount, 'details': [], 'number' : number}
    for detail in order.details:
        detail_dict = {'detail': detail.text, 'image_path': detail.image_path}
        order_dict['details'].append(detail_dict)
    return jsonify(order_dict)

@app.route('/user/<user_id>/image_collection', methods=['POST'])
def add_image_to_collection(user_id):
    data = request.json
    image_id = data['image_id']
    user = User.query.get(user_id)
    if user is None:
        return jsonify({'error': 'User not found'})
    image = Image.query.get(image_id)
    if image is None:
        return jsonify({'error': 'Image not found'})
    if image in user.collections:
        user.collections.remove(image) # If it is, remove it
    else:
        user.collections.append(image) # If it isn't, add it
    db.session.add(user)
    db.session.commit()
    db.session.add(user)
    db.session.commit()
    return jsonify({'success': True})
@app.route('/user/collected_images', methods=['POST'])
def get_collected_images():
    data = request.json
    user_id = data['user_id']
    user = User.query.get(user_id)
    if user is None:
        return jsonify({'error': 'User not found'})
    images = user.collections
    return jsonify([{'id': i.id, 'name': i.name, 'thumb': i.thumb, 'src': i.src, 'category' : i.category} for i in images])

if __name__ == '__main__':
    app.run()
