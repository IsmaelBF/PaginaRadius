from flask import Flask, render_template, request, redirect, url_for
from datetime import date, datetime
from database import get_connection, init_db

app = Flask(__name__)
USUARIO_ACTUAL_ID = 1

def calcular_readiness(horas, calidad):
    score = int((horas / 8.0) * 60 + (calidad / 5.0) * 40)
    score = min(100, max(0, score))
    if score >= 85:
        return score, "Óptimo", "Listo para sobrecarga progresiva (100% intensidad).", "emerald"
    elif score >= 65:
        return score, "Moderado", "Energía media. Mantén pesos pero deja RIR 2-3.", "amber"
    else:
        return score, "Fatiga Alta", "Descanso bajo. Reduce cargas 15% o prioriza movilidad.", "rose"

# 1. PANTALLA PRINCIPAL: AGENDA DEL DÍA
@app.route("/", methods=["GET"])
def agenda():
    conn = get_connection()
    cursor = conn.cursor()
    hoy = date.today().isoformat()

    cursor.execute("""
        SELECT id, hora_inicio, titulo, tipo, completada
        FROM actividades_agenda
        WHERE usuario_id = ? AND fecha = ?
        ORDER BY hora_inicio ASC
    """, (USUARIO_ACTUAL_ID, hoy))
    actividades = cursor.fetchall()

    conn.close()
    return render_template("agenda.html", actividades=actividades, fecha_hoy=hoy)

@app.route("/agregar-actividad", methods=["POST"])
def agregar_actividad():
    titulo = request.form.get("titulo")
    hora_inicio = request.form.get("hora_inicio")
    tipo = request.form.get("tipo")
    descripcion = request.form.get("descripcion")
    hoy = date.today().isoformat()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO actividades_agenda (usuario_id, fecha, hora_inicio, titulo, descripcion, tipo)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (USUARIO_ACTUAL_ID, hoy, hora_inicio, titulo, descripcion, tipo))
    conn.commit()
    conn.close()
    return redirect(url_for("agenda"))

# 2. DETALLE DE CADA ACTIVIDAD AL DAR CLIC
@app.route("/actividad/<int:actividad_id>", methods=["GET"])
def detalle_actividad(actividad_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM actividades_agenda
        WHERE id = ? AND usuario_id = ?
    """, (actividad_id, USUARIO_ACTUAL_ID))
    actividad = cursor.fetchone()
    conn.close()

    if not actividad:
        return redirect(url_for("agenda"))

    return render_template("detalle_actividad.html", actividad=actividad)

@app.route("/completar-actividad/<int:actividad_id>", methods=["POST"])
def completar_actividad(actividad_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE actividades_agenda
        SET completada = NOT completada
        WHERE id = ? AND usuario_id = ?
    """, (actividad_id, USUARIO_ACTUAL_ID))
    conn.commit()
    conn.close()
    return redirect(url_for("detalle_actividad", actividad_id=actividad_id))

# 3. APARTADO DE GIMNASIO (Consulta el sueño como extra)
@app.route("/gimnasio", methods=["GET"])
def gimnasio():
    conn = get_connection()
    cursor = conn.cursor()
    hoy = date.today().isoformat()

    cursor.execute("""
        SELECT e.id, e.nombre, m.nombre AS musculo 
        FROM ejercicios e
        JOIN musculos m ON e.musculo_principal_id = m.id
        ORDER BY m.nombre, e.nombre
    """)
    ejercicios = cursor.fetchall()

    # Consulta extra: ver cómo durmió hoy para mostrar recomendación en el gym
    cursor.execute("""
        SELECT horas_dormidas, calidad_subjetiva FROM registro_sueno 
        WHERE usuario_id = ? AND fecha = ?
    """, (USUARIO_ACTUAL_ID, hoy))
    sueno = cursor.fetchone()

    readiness = None
    if sueno:
        score, estado, mensaje, color = calcular_readiness(sueno["horas_dormidas"], sueno["calidad_subjetiva"])
        readiness = {"score": score, "estado": estado, "mensaje": mensaje, "color": color}

    cursor.execute("""
        SELECT s.id, e.nombre AS ejercicio, s.numero_serie, s.peso_kg, s.repeticiones
        FROM series_realizadas s
        JOIN sesiones_entrenamiento ses ON s.sesion_id = ses.id
        JOIN ejercicios e ON s.ejercicio_id = e.id
        WHERE ses.usuario_id = ? AND DATE(ses.fecha_inicio) = ?
        ORDER BY s.id DESC
    """, (USUARIO_ACTUAL_ID, hoy))
    series_hoy = cursor.fetchall()

    conn.close()
    return render_template("gimnasio.html", ejercicios=ejercicios, readiness=readiness, series_hoy=series_hoy)

@app.route("/registrar-serie", methods=["POST"])
def registrar_serie():
    ejercicio_id = int(request.form.get("ejercicio_id"))
    peso_kg = float(request.form.get("peso_kg"))
    repeticiones = int(request.form.get("repeticiones"))
    hoy = date.today().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM sesiones_entrenamiento WHERE usuario_id = ? AND DATE(fecha_inicio) = ?", (USUARIO_ACTUAL_ID, hoy))
    sesion = cursor.fetchone()
    if sesion:
        sesion_id = sesion["id"]
    else:
        cursor.execute("INSERT INTO sesiones_entrenamiento (usuario_id, fecha_inicio) VALUES (?, ?)", (USUARIO_ACTUAL_ID, datetime.now().isoformat()))
        sesion_id = cursor.lastrowid

    cursor.execute("SELECT COUNT(*) AS total FROM series_realizadas WHERE sesion_id = ? AND ejercicio_id = ?", (sesion_id, ejercicio_id))
    numero_serie = cursor.fetchone()["total"] + 1

    cursor.execute("INSERT INTO series_realizadas (sesion_id, ejercicio_id, numero_serie, peso_kg, repeticiones) VALUES (?, ?, ?, ?, ?)",
                   (sesion_id, ejercicio_id, numero_serie, peso_kg, repeticiones))
    conn.commit()
    conn.close()
    return redirect(url_for("gimnasio"))

# 4. APARTADO INDEPENDIENTE DE SUEÑO
@app.route("/sueno", methods=["GET", "POST"])
def sueno():
    conn = get_connection()
    cursor = conn.cursor()
    hoy = date.today().isoformat()

    if request.method == "POST":
        horas = float(request.form.get("horas_dormidas"))
        calidad = int(request.form.get("calidad_subjetiva"))
        score, _, _, _ = calcular_readiness(horas, calidad)

        cursor.execute("""
            INSERT INTO registro_sueno (usuario_id, fecha, horas_dormidas, calidad_subjetiva, score_preparacion)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(usuario_id, fecha) DO UPDATE SET
                horas_dormidas = excluded.horas_dormidas,
                calidad_subjetiva = excluded.calidad_subjetiva,
                score_preparacion = excluded.score_preparacion
        """, (USUARIO_ACTUAL_ID, hoy, horas, calidad, score))
        conn.commit()
        conn.close()
        return redirect(url_for("sueno"))

    cursor.execute("SELECT * FROM registro_sueno WHERE usuario_id = ? ORDER BY fecha DESC LIMIT 7", (USUARIO_ACTUAL_ID,))
    historial_sueno = cursor.fetchall()
    conn.close()
    return render_template("sueno.html", historial=historial_sueno, fecha_hoy=hoy)

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)