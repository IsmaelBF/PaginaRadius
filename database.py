import sqlite3
from datetime import datetime

DB_NAME = "fit_tracker.db"

def get_connection():
    """
    Crea y retorna una conexión a SQLite con las llaves foráneas activadas.
    Nota: En SQLite, PRAGMA foreign_keys está apagado por defecto en cada conexión.
    """
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Permite acceder a columnas por nombre (ej. fila['nombre'])
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """Crea las tablas normalizadas y carga datos iniciales de catálogo."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Tabla de Usuarios (para soportar múltiples alumnos/usuarios en el servidor RADIUS)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        nombre_completo TEXT NOT NULL,
        fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Catálogo de Grupos Musculares (Base para el cálculo de recuperación)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS musculos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL UNIQUE,
        horas_recuperacion_base INTEGER NOT NULL DEFAULT 48
    );
    """)

    # 3. Catálogo de Ejercicios (Normalizado: apunta al músculo principal)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ejercicios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL UNIQUE,
        musculo_principal_id INTEGER NOT NULL,
        descripcion TEXT,
        FOREIGN KEY (musculo_principal_id) REFERENCES musculos(id) ON DELETE RESTRICT
    );
    """)

    # 4. Rutinas (Plantillas creadas por cada usuario)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rutinas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        nombre TEXT NOT NULL,
        objetivo TEXT, -- Ej: Hipertrofia, Fuerza, Resistencia
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
    );
    """)

    # 5. Tabla Intermedia: Rutina <-> Ejercicios (Relación N:M normalizada)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rutina_ejercicios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rutina_id INTEGER NOT NULL,
        ejercicio_id INTEGER NOT NULL,
        orden INTEGER NOT NULL DEFAULT 1,
        series_objetivo INTEGER NOT NULL DEFAULT 3,
        reps_objetivo INTEGER NOT NULL DEFAULT 10,
        FOREIGN KEY (rutina_id) REFERENCES rutinas(id) ON DELETE CASCADE,
        FOREIGN KEY (ejercicio_id) REFERENCES ejercicios(id) ON DELETE RESTRICT
    );
    """)

    # 6. Sesiones de Entrenamiento (Cada vez que el usuario va al gimnasio)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sesiones_entrenamiento (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        rutina_id INTEGER, -- Puede ser NULL si hizo un entrenamiento libre
        fecha_inicio TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        fecha_fin TIMESTAMP,
        notas TEXT,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
        FOREIGN KEY (rutina_id) REFERENCES rutinas(id) ON DELETE SET NULL
    );
    """)

    # 7. Series Realizadas (Registro atómico de cada levantamiento)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS series_realizadas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sesion_id INTEGER NOT NULL,
        ejercicio_id INTEGER NOT NULL,
        numero_serie INTEGER NOT NULL,
        peso_kg REAL NOT NULL CHECK (peso_kg >= 0),
        repeticiones INTEGER NOT NULL CHECK (repeticiones > 0),
        rir INTEGER, -- Repeticiones en recámara (opcional, útil para hipertrofia)
        completada BOOLEAN NOT NULL DEFAULT 1,
        FOREIGN KEY (sesion_id) REFERENCES sesiones_entrenamiento(id) ON DELETE CASCADE,
        FOREIGN KEY (ejercicio_id) REFERENCES ejercicios(id) ON DELETE RESTRICT
    );
    """)

    # 8. Registro de Sueño (Base para el Readiness Score y ajuste de rutina)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS registro_sueno (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        fecha DATE NOT NULL,
        horas_dormidas REAL NOT NULL CHECK (horas_dormidas > 0 AND horas_dormidas <= 24),
        calidad_subjetiva INTEGER NOT NULL CHECK (calidad_subjetiva BETWEEN 1 AND 5),
        score_preparacion INTEGER, -- Calculado (0 a 100)
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
        UNIQUE(usuario_id, fecha) -- Evita registrar dos veces el sueño del mismo día
    );
    """)
    # 9. Agenda Diaria (Núcleo principal de actividades vinculable a rutinas)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS actividades_agenda (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        fecha DATE NOT NULL,
        hora_inicio TEXT NOT NULL, -- Formato 'HH:MM'
        titulo TEXT NOT NULL,
        descripcion TEXT,
        tipo TEXT NOT NULL DEFAULT 'general', -- 'general', 'tarea', 'gimnasio'
        rutina_id INTEGER, -- Opcional: vincula la actividad con una rutina si tipo == 'gimnasio'
        completada BOOLEAN NOT NULL DEFAULT 0,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
        FOREIGN KEY (rutina_id) REFERENCES rutinas(id) ON DELETE SET NULL
    );
    """)

    conn.commit()
    seed_initial_data(conn)
    conn.close()
    print(f"[OK] Base de datos '{DB_NAME}' inicializada y normalizada correctamente.")

def seed_initial_data(conn):
    """Inserta datos base (catálogo de músculos, ejercicios y usuario demo) si está vacía."""
    cursor = conn.cursor()

    # Verificar si ya existen músculos para no duplicar en cada arranque
    cursor.execute("SELECT COUNT(*) FROM musculos")
    if cursor.fetchone()[0] > 0:
        return

    # Catálogo inicial de músculos y tiempo estimado de recuperación
    musculos = [
        ("Pecho", 48),
        ("Espalda", 72),
        ("Cuádriceps", 72),
        ("Isquiotibiales", 72),
        ("Hombros", 48),
        ("Bíceps", 36),
        ("Tríceps", 36),
        ("Abdomen", 24)
    ]
    cursor.executemany(
        "INSERT INTO musculos (nombre, horas_recuperacion_base) VALUES (?, ?)",
        musculos
    )

    # Catálogo inicial de ejercicios básicos (usando los IDs insertados arriba: 1=Pecho, 2=Espalda, etc.)
    ejercicios = [
        ("Press de Banca Plano", 1, "Empuje horizontal con barra"),
        ("Press Inclinado con Mancuernas", 1, "Enfoque en haz clavicular"),
        ("Remo con Barra", 2, "Tracción horizontal para densidad de espalda"),
        ("Jalón al Pecho", 2, "Tracción vertical para dorsal ancho"),
        ("Sentadilla Libre", 3, "Ejercicio compuesto dominante de rodilla"),
        ("Peso Muerto Rumano", 4, "Bisagra de cadera para cadena posterior"),
        ("Press Militar", 5, "Empuje vertical para deltoide anterior"),
        ("Curl de Bíceps con Barra", 6, "Flexión de codo"),
        ("Extensión de Tríceps en Polea", 7, "Extensión de codo")
    ]
    cursor.executemany(
        "INSERT INTO ejercicios (nombre, musculo_principal_id, descripcion) VALUES (?, ?, ?)",
        ejercicios
    )

    # Usuario de prueba inicial
    cursor.execute(
        "INSERT INTO usuarios (username, nombre_completo) VALUES (?, ?)",
        ("ismael", "Ismael Balcazar")
    )

    conn.commit()
    print("[OK] Datos iniciales de catálogo insertados.")

if __name__ == "__main__":
    init_db()