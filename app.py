import pandas as pd

import streamlit as st
from streamlit_folium import st_folium
import folium
from geopy.distance import geodesic
from st_aggrid import AgGrid, GridOptionsBuilder
from vision_helper import Basuras
import ast

st.set_page_config(layout="wide")
st.sidebar.image("logo.png", use_container_width=True)

# HTML para fijar nombres al fondo del sidebar, centrados
st.sidebar.markdown(
    """
    <style>
    .sidebar-bottom {
        position: fixed;
        bottom: 0;
        width: 20%;
        text-align: center;
        padding-bottom: 20px;
        color: #6c757d;
    }
    </style>
    <div class='sidebar-bottom'>
        <p>Carolina González Marín</p>
        <p>Christian Felipe Alzate Cardona</p>
        <p>Johanna Zuluaga Quiros</p>
        <p>Wiston Danobys Mazo Quintero</p>
    </div>
    """,
    unsafe_allow_html=True
)
st.markdown("<h1 style='text-align: center;'>Evaluación de la Limpieza Urbana en las Calles de Medellín</h1>", unsafe_allow_html=True)
st.markdown("A continuación realizarás un análisis de una zona específica en **Medellín**. Para ello, selecciona en el mapa el **punto central** de la zona que deseas analizar. Luego, en la parte lateral, indica la **distancia** (radio del área a analizar) y el **step** (espaciado entre puntos dentro del área). Recuerda que **solo se permiten puntos dentro del área delimitada en el mapa**. Si conoces las coordenadas exactas del lugar que deseas analizar, también puedes ingresarlas manualmente.")

# Centro de Medellín
centro_medellin = [6.2442, -75.5812]
radio_km = 8

col1, col2 = st.columns([2, 1])  # Más espacio al mapa

with col1:
    m = folium.Map(location=centro_medellin, zoom_start=12)
    folium.Circle(
        location=centro_medellin,
        radius=radio_km * 1000,
        color='purple',
        fill=True,
        fill_opacity=0.05
    ).add_to(m)
    m.add_child(folium.LatLngPopup())
    map_data = st_folium(m, width=700, height=500)

# Inicializar valores por defecto
auto_lat, auto_lon = None, None

with col2:
    if map_data and map_data.get("last_clicked"):
        coords = map_data["last_clicked"]
        latlon = (coords["lat"], coords["lng"])
        distancia_seleccion = geodesic(latlon, centro_medellin).km

        if distancia_seleccion <= radio_km:
            st.success(f"El punto seleccionado es válido ({coords['lat']:.6f}, {coords['lng']:.6f}). Puedes proceder con el análisis")
            auto_lat, auto_lon = coords["lat"], coords["lng"]
        else:
            st.error(f"El punto seleccionado está fuera del área permitida ({distancia_seleccion:.2f} km del centro). Selecciona un punto dentro de la zona delimitada")
    if 'df' not in st.session_state:
        st.session_state.df = pd.DataFrame()

    with st.form(key='parametros_form'):
        latitud = st.number_input("Latitud", format="%.6f", value=auto_lat if auto_lat else 0.0)
        longitud = st.number_input("Longitud", format="%.6f", value=auto_lon if auto_lon else 0.0)
        distancia = st.number_input("Distancia (metros)", min_value=100, step=1)
        step = st.number_input("Paso (metros)", min_value=10, step=1)
        submit_button = st.form_submit_button(label='Realizar análisis')

    if submit_button:
        if all([latitud, longitud, distancia, step]):
            with st.spinner("Generando puntos, capturando imágenes, realizando análisis..."):
                latitud_str = str(latitud).replace(",",".")
                longitud_str = str(longitud).replace(",",".")
                st.session_state.df = Basuras().buscar_basuras_en_zona(latitud_str, longitud_str, distancia, step)
                
                st.success("Análisis completado con éxito.")
        else:
            st.error("Por favor, complete todos los campos correctamente.")

# Procesamiento del DataFrame
if not st.session_state.df.empty:
    df = st.session_state.df

    df['Description'] = df['Description'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
    desc_df = pd.json_normalize(df['Description'])
    df = pd.concat([df.drop(columns=['Description']), desc_df], axis=1)

    def calcular_iplu(fila):
        intensidad_puntos = {'No': 0, 'leve': 1, 'moderada': 2, 'alta': 3}
        urgencia_puntos = {'No urgente': 0, 'Moderadamente urgente': 2, 'Urgente': 4}
        acumulacion_basura = {'Sí': 2, 'No': 0}

        nsv_1 = abs(fila['limpieza_general'] - 10)
        nsv = nsv_1 * 2 if nsv_1 <= 6 else nsv_1 * 0.5
        aeb = intensidad_puntos.get(fila['intensidad_basura'], 0)
        acb = acumulacion_basura.get(fila['acumulacion_basura'], 0)
        ur = urgencia_puntos.get(fila['recoleccion_urgente'], 0)
        pcv = 0 if fila['papeleras_presentes'] == 'Sí' else 2

        return nsv + aeb + ur + pcv + acb

    df['IPLU'] = df.apply(calcular_iplu, axis=1)

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align: center;'>Análisis Exploratorio: Evaluación del IPLU y Variables Clave</h2>", unsafe_allow_html=True)
    st.markdown(f"""
        <div style="
            text-align: center;
            background-color: #CBB4F2;
            color: #101218;
            font-size: 25px;
            padding: 2px;
            border-radius: 2px;
            border-left: 10px solid #00BFC2;
            margin-top: 10px;
        ">
            <strong>Imágenes válidas para el análisis: {df["es_imagen_valida"].sum()} ({100*(df["es_imagen_valida"].sum())/len(df)}%)</strong>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)

    nuevos_nombres = {
        'Latitude': 'Latitud',
        'Longitude': 'Longitud',
        'es_imagen_valida': 'Imagen Válida',
        'limpieza_general': 'Limpieza General',
        'acumulacion_basura': 'Acumulación de Basura',
        'intensidad_basura': 'Intensidad de Basura',
        'recoleccion_urgente': 'Recolección Urgente',
        'papeleras_presentes': 'Papeleras Presentes',
        'justificacion': 'Justificación',
        'IPLU': 'IPLU',
        'Image': 'Imagen',
        'Label': 'Clasificación (YOLO)'
    }
    df = df.rename(columns=nuevos_nombres)

    with col1:
        st.markdown("<h4 style='text-align: center;'>Limpieza General</h4>", unsafe_allow_html=True)
        st.bar_chart(df['Limpieza General'].value_counts().sort_index())
    with col2:
        st.markdown("<h4 style='text-align: center;'>Intensidad de Basura</h4>", unsafe_allow_html=True)
        st.bar_chart(df['Intensidad de Basura'].value_counts())
    with col3:
        st.markdown("<h4 style='text-align: center;'>Urgencia de Recolección</h4>", unsafe_allow_html=True)
        st.bar_chart(df['Recolección Urgente'].value_counts())

    col4, col5, col6 = st.columns(3)
    with col4:
        conteo = df['Papeleras Presentes'].value_counts().sort_index()
        porcentaje = (conteo / conteo.sum()) * 100

        tabla_resumen = pd.DataFrame({
            'Cantidad': conteo,
            'Porcentaje (%)': porcentaje.round(1)
        }).reset_index().rename(columns={'index': 'Categoría'})

        # Mostrar la tabla
        st.markdown("<h4 style='text-align: center;'>Presencia de Contenedores de Basura</h4>", unsafe_allow_html=True)
        st.table(tabla_resumen)

    with col5:
        conteo = df['Acumulación de Basura'].value_counts().sort_index()
        porcentaje = (conteo / conteo.sum()) * 100

        tabla_resumen = pd.DataFrame({
            'Cantidad': conteo,
            'Porcentaje (%)': porcentaje.round(1)
        }).reset_index().rename(columns={'index': 'Categoría'})

        # Mostrar la tabla
        st.markdown("<h4 style='text-align: center;'>Acumulación de Basura</h4>", unsafe_allow_html=True)
        st.table(tabla_resumen)
    
    with col6:
        conteo = df['Clasificación (YOLO)'].value_counts().sort_index()
        porcentaje = (conteo / conteo.sum()) * 100

        tabla_resumen = pd.DataFrame({
            'Cantidad': conteo,
            'Porcentaje (%)': porcentaje.round(1)
        }).reset_index().rename(columns={'index': 'Categoría'})

        # Mostrar la tabla
        st.markdown("<h4 style='text-align: center;'>Clasificación (YOLO)</h4>", unsafe_allow_html=True)
        st.table(tabla_resumen)
    
    st.markdown("<h3 style='text-align: center;'>Índice de Priorización de Limpieza Urbana (IPLU)</h3>", unsafe_allow_html=True)
    # Clasificación según el valor
    iplu_valor = round(df['IPLU'].mean(), 2)
    if iplu_valor <= 5:
        nivel = "Baja Prioridad"
        descripcion = "Zona limpia. Se recomienda monitoreo regular."
        color = "#4CAF50"  # verde
    elif iplu_valor <= 10:
        nivel = "Media Prioridad"
        descripcion = "Zona con cierta acumulación de residuos. Se requiere seguimiento frecuente."
        color = "#FFC107"  # amarillo
    elif iplu_valor <= 15:
        nivel = "Alta Prioridad"
        descripcion = "Zona con acumulación significativa de basura. Atención urgente necesaria."
        color = "#FF5722"  # naranja
    else:
        nivel = "Crítica"
        descripcion = "Zona en condiciones críticas de limpieza. Se requiere intervención inmediata."
        color = "#F44336"  # rojo

    # === Sección organizada en columnas ===
    col1, col2, = st.columns([1, 5])

    with col1:
        st.markdown(f"""
        <div style='
            background-color: {color};
            padding: 2px;
            border-radius: 12px;
            text-align: center;
            color: white;
            font-size: 35px;
            font-weight: bold;
        '>
            IPLU<br>{round(iplu_valor, 2)}
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div style='
            background-color: #f0f0f0;
            padding: 2px;
            border-radius: 12px;
            text-align: center;
            color: black;
        '>
            <h4 style='color: {color}; margin-bottom: 10px;'>{nivel}</h4>
            <p style='font-size: 20px;'>{descripcion}</p>
        </div>
        """, unsafe_allow_html=True)

    columnas_a_mostrar = list(nuevos_nombres.values())

    st.markdown("<hr>", unsafe_allow_html=True)

    col5, col4 = st.columns([4, 1])
    with col5:
        st.markdown("<h3 style='text-align: center;'>Detalle de Información Empleada para el Análisis</h3>", unsafe_allow_html=True)
    with col4:
        csv = df.to_csv(index=False).encode('utf-8')

        # Botón de descarga
        st.download_button(
            label="📥 Descargar CSV",
            data=csv,
            file_name='datos.csv',
            mime='text/csv'
        )

    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_selection('single', use_checkbox=True)
    grid_options = gb.build()

    grid_response = AgGrid(
        df, 
        gridOptions=grid_options, 
        height=300, 
        width='100%', 
        reload_data=True
    )

    # Obtener la selección
    selected = grid_response.get('selected_rows', None)

    # Manejar la selección según su tipo
    if isinstance(selected, pd.DataFrame):
        if selected.empty:
            st.info("Selecciona una fila para ver la imagen.")
        else:
            fila = selected.iloc[0]
    elif isinstance(selected, list):
        if len(selected) == 0:
            st.info("Selecciona una fila para ver la imagen.")
        else:
            fila = selected[0]
    else:
        st.info("Selecciona una fila para ver la imagen.")
        fila = None

    # Si se obtuvo una fila, extraer la ruta y mostrar la imagen
    if fila is not None:
        ruta = fila.get('Imagen', None)
        if ruta:
            # Eliminar el prefijo './' (puedes usar removeprefix en Python 3.9+)
            ruta_relativa = ruta.lstrip("./")
            st.image(ruta_relativa, caption=f"Coordenadas: {fila.get('Latitud', None)}, {fila.get('Longitud', None)}", use_container_width=False)
            st.write(f"{fila.get('Justificación')}")
            
        else:
            st.warning("La fila seleccionada no contiene la ruta de la imagen.")
                
else:
    st.info("Ingrese los parámetros solicitados para poder realizar el análisis")



