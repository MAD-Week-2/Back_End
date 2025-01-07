from flask import Flask, request, jsonify
from flask_bcrypt import Bcrypt
from flask_cors import CORS
import mysql.connector
from dotenv import load_dotenv
import os

app = Flask(__name__)
CORS(app)
bcrypt = Bcrypt(app)
load_dotenv()

# MySQL 데이터베이스 연결 설정 (환경 변수에서 불러오기)
db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": int(os.getenv("DB_PORT", 3306))  # 포트는 기본값 3306
}
@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    username = data['username']
    password = data['password']
    
    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400
    
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

    conn = None  # 초기화
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, hashed_password)
        )
        conn.commit()
        return jsonify({'message': 'User created successfully'}), 201
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 400
    finally:
        if conn and conn.is_connected():  # conn이 None이 아니고 연결된 경우에만 닫기
            cursor.close()
            conn.close()


@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data['username']
    password = data['password']

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()

        if user and bcrypt.check_password_hash(user[0], password):
            return jsonify({'success' : True, 'message': 'success'}), 200
        else:
            return jsonify({'success' : False, 'message': 'Invalid credentials'}), 401
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/record_late', methods=['POST'])
def record_late():
    try:
        
        data = request.json
        user_id = data.get('user_id')

        if not user_id:
            return jsonify({"error": "User ID is required"}), 400

        from datetime import date
        today = date.today()

        # MySQL 연결
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        
        query = """
            INSERT INTO late_records (user_id, late_date) 
            VALUES (%s, %s)
        """
        cursor.execute(query, (user_id, today))
        conn.commit()

        # 응답
        return jsonify({"message": "Late record saved successfully", "user_id": user_id, "late_date": str(today)}), 201

    except mysql.connector.Error as err:
        return jsonify({"error": f"MySQL error: {err}"}), 500

    except Exception as e:
        return jsonify({"error": f"Unexpected error: {e}"}), 500

    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
            

@app.route('/get_late_count', methods=['GET'])
def get_late_count():
    try:
        
        user_id = request.args.get('user_id')
        print(f"Received user_id: {user_id}")

        if not user_id:
            return jsonify({"error": "User ID is required"}), 400

        # MySQL 연결
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        query = """
            SELECT COUNT(*) AS late_count 
            FROM late_records 
            WHERE user_id = %s
        """
        cursor.execute(query, (user_id,))
        result = cursor.fetchone()

        # 응답 생성
        response = {
            "user_id": user_id,
            "late_count": result[0]
        }
        return jsonify(response), 200

    except mysql.connector.Error as err:
        return jsonify({"error": f"MySQL error: {err}"}), 500

    except Exception as e:
        return jsonify({"error": f"Unexpected error: {e}"}), 500

    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()



# API: 주변 정류소 정보와 자전거 대수 반환
@app.route('/get_nearby_stations', methods=['POST'])
def get_nearby_stations():
    try:
    
        data = request.json
        user_lat = data.get('latitude')
        user_lng = data.get('longitude')
        user_id = data.get('id')

        if not all([user_lat, user_lng, user_id]):
            return jsonify({"error": "Missing latitude, longitude, or id"}), 400

        # MySQL 연결
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

   
        query = """
            SELECT
                station_id,
                station_name,
                location_lat,
                location_lng,
                available_bikes,
                capacity,
                ST_Distance_Sphere(
                    POINT(location_lng, location_lat), 
                    POINT(%s, %s)
                ) AS distance
            FROM locations
            WHERE ST_Distance_Sphere(
                    POINT(location_lng, location_lat), 
                    POINT(%s, %s)
                ) < 1000; -- 반경 1km
        """
        cursor.execute(query, (user_lng, user_lat, user_lng, user_lat))
        stations = cursor.fetchall()
        print(cursor.fetchall())
        
        for station in stations:
            if isinstance(station['station_name'], bytes):
                station['station_name'] = station['station_name'].decode('utf-8')

        # 응답 생성
        response = {
            "user_id": user_id,
            "latitude": user_lat,
            "longitude": user_lng,
            "nearby_stations": stations
        }

        return jsonify(response)

    except mysql.connector.Error as err:
        return jsonify({"error": f"MySQL error: {err}"}), 500

    except Exception as e:
        return jsonify({"error": f"Unexpected error: {e}"}), 500

    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
            
@app.route('/get_stations_in_bounds', methods=['POST'])
def get_stations_in_bounds():
    try:
        # 사용자 입력 받기
        data = request.json
        map_lat = data.get('latitude')
        map_lng = data.get('longitude')

        if not all([map_lat, map_lng]):
            return jsonify({"error": "Missing latitude or longitude"}), 400

        # MySQL 연결
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

       
        query = """
            SELECT
                location_lat,
                location_lng,
                available_bikes
            FROM locations
        """
        cursor.execute(query)
        stations = cursor.fetchall()

        # 응답 생성
        response = []
        for station in stations:
            response.append({
                "location_lat": station['location_lat'],
                "location_lng": station['location_lng'],
                "available_bikes": station['available_bikes']
            })

        return jsonify(response), 200

    except mysql.connector.Error as err:
        return jsonify({"error": f"MySQL error: {err}"}), 500

    except Exception as e:
        return jsonify({"error": f"Unexpected error: {e}"}), 500

    finally:
        if conn.is_connected():
            cursor.close()
        


if __name__ == '__main__':
    app.run(debug=True, port=5001)
