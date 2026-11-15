from flask import Flask, render_template, request, jsonify
import sqlite3

app = Flask(__name__)

# Ruta principal que carga la interfaz
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    # host='0.0.0.0' permite conexiones desde otros dispositivos en la red local
    app.run(host='0.0.0.0', port=5000, debug=True)