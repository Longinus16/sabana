import base64
import pyodbc
from urllib.parse import quote as urlquote
from flask import Flask, send_from_directory
import dash
import dash_leaflet as dl
import dash_cytoscape as cyto

from dash import dcc, html, Input, Output, State, ALL,dash_table
import os
import re
import dash_leaflet.express as dlx
from datetime import datetime, timedelta
import io
import pandas as pd
import numpy as np
import warnings
import time
import plotly.graph_objects as go
import random
import dash_auth
cyto.load_extra_layouts()
warnings.filterwarnings("ignore")
pressed_buttons = {}
directorio_actual = os.getcwd()
nombre_directorio = "app_uploaded_files"
VALID_USERNAME_PASSWORD_PAIRS = {
    'usuario': 'contraseña'
}

UPLOAD_DIRECTORY = os.path.join(directorio_actual, nombre_directorio)
if not os.path.exists(UPLOAD_DIRECTORY):
    os.makedirs(UPLOAD_DIRECTORY)

def dms_to_decimal(dms):
    if isinstance(dms, float):
        return dms
    else:
        match = re.search(r"(\d+)°(\d+)'([\d\.]+)\"([NSEW])", dms)
        if(match == None):
            match = re.search(r"(\d+)�(\d+)'([\d\.]+)\"([NSEW])", dms)
        if match:
            degrees, minutes, seconds, direction = match.groups()
            decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
            if direction in ['S', 'W']:
                decimal = -decimal
            return decimal
        else:
            return None

def prepare_df(path):
    columnas = ["Destino","Fecha", "Hora","Latitud","Longitud"]
    path = f'{path}'
    if "csv" in path:
        sabana = pd.read_csv(path)
    elif "xlsx" in path:
        sabana = pd.read_excel(path)
    else:
        return None
    for idx, column_name in enumerate(sabana):
        column = column_name.lower()
        if "fecha de la comunicación" == column:
            sabana['Fecha'] = sabana[column_name]
        if "fecha" == column:
            sabana['Fecha'] = sabana[column_name]
        if "hora de la comunicación" == column:
            sabana['Hora'] = sabana[column_name]
        if "hora" == column:
            sabana['Hora'] = sabana[column_name]
        if "latitud" == column:
            sabana['Latitud'] = sabana[column_name]
        if "longitud" == column:
            sabana['Longitud'] = sabana[column_name]
        if "LATITUD" == column:
            sabana['Latitud'] = sabana[column_name]
        if "LONGITUD" == column:
            sabana['Longitud'] = sabana[column_name]
        if "número destino" == column:
            sabana['Destino'] = sabana[column_name]
        if "numero b" == column:
            sabana['Destino'] = sabana[column_name]
        if "ubicacion geografica (latitud / longitud)" == column:
            sabana['Latitud'] = sabana.iloc[:,idx]
            sabana['Longitud'] = sabana.iloc[:,idx+1]
            sabana['Latitud'] = sabana['Latitud'].apply(dms_to_decimal)
            sabana['Longitud'] = sabana['Longitud'].apply(dms_to_decimal)
    formato = str(sabana.at[0, 'Fecha'])  
    if "-" in formato:
        formato = '%Y-%m-%d'
    elif "/" in formato:
        formato = '%d/%m/%Y'
        
    sabana['Fecha'] = pd.to_datetime(sabana['Fecha'], format=formato, errors='coerce')
    sabana = sabana.drop_duplicates(subset=columnas)
    sabana = sabana.dropna(subset=["Latitud","Longitud"])
    sabana = sabana[sabana['Latitud'].astype(str).str.contains('\.') & sabana['Longitud'].astype(str).str.contains('\.')]
    sabana["Latitud"] = sabana["Latitud"].astype(float)
    sabana["Longitud"] = sabana["Longitud"].astype(float)
    return sabana[columnas]

server = Flask(__name__)
app = dash.Dash(server=server)
auth = dash_auth.BasicAuth(
    app,
    VALID_USERNAME_PASSWORD_PAIRS
)
@server.route("/download/<path:path>")
def download(path):
    """Serve a file from the upload directory."""
    return send_from_directory(UPLOAD_DIRECTORY, path, as_attachment=True)

def save_file(name, content):
    data = content.encode("utf8").split(b";base64,")[1]
    with open(os.path.join(UPLOAD_DIRECTORY, name), "wb") as fp:
        fp.write(base64.decodebytes(data))

def uploaded_files():
    files = []
    for filename in os.listdir(UPLOAD_DIRECTORY):
        path = os.path.join(UPLOAD_DIRECTORY, filename)
        if os.path.isfile(path):
            files.append(filename)
    return files


def file_download_link(filename):
    location = "/download/{}".format(urlquote(filename))
    return html.A(filename, href=location)

@app.callback(
    [Output("opciones", "children"),
     Output("file-list", "children")],
    [Input("upload-data", "contents"),
     Input('upload-data', 'filename'),
     Input('btn-limpiar', 'n_clicks')],
    [State("upload-data", "contents"),
     State("upload-data", "filename")]
)
def update_output(contents, filenames, n_clicks, current_contents, current_filenames):
    if n_clicks is not None:
        return [], [html.Li("Archivo borrado")]

    if filenames is not None and contents is not None:
        for name, data in zip(filenames, contents):
            save_file(name, data)

    files = uploaded_files()
    if len(files) == 0:
        return [], [html.Li("Sin archivo!")]
    else:
        file_list = [html.Li(file_download_link(filename)) for filename in files]
        opciones = [html.Button(f, id={'type': 'boton', 'filename': f}, style={"color":"white","box-shadow": "2px 2px 4px rgba(0, 0, 0, 0.5)","border-radius": "50px", "margin-right": "10px","width": "200px","height":"40px","background-color":"#83a5f0"}) for f in files]
        return opciones, file_list

    
def validate_ddays(disabled_days, dates_disabled):
    disabled_days_values = list(filter(lambda day: day not in dates_disabled, disabled_days))
    return disabled_days_values

def truncate_float(x, decimals=5):
    s = str(x)
    decimal_index = s.find('.')
    if decimal_index != -1:
        s = s[:decimal_index + decimals + 1]
    return float(s)

def encontrar_coincidencias(df2, fecha_elegida,selected_hour):
    df2 = df2[df2['Fecha'] == fecha_elegida]
    df2 = df2[df2['Hora'].str[:2].astype(int) <= selected_hour]
    df2['Latitud'] = df2['Latitud'].apply(truncate_float).astype(float)
    df2['Longitud'] = df2['Longitud'].apply(truncate_float).astype(float)
    df2["HoraInt"] = df2['Hora'].str[:2].astype(int)
    df2 = df2.drop_duplicates(subset=['Latitud', 'Longitud', 'file']).reset_index(drop=True)
    df2['Pareja'] = df2.groupby(['Latitud', 'Longitud','file']).cumcount() + 1
    df2['Indices'] = df2.groupby(['Latitud', 'Longitud'])['Latitud'].transform(lambda x: ','.join(map(str, x.index)))
    df2 = df2[df2['Indices'].str.split(',').apply(len) > 1]
    df2 = df2.drop_duplicates(subset=['Indices'])
    duplicated = df2.copy()
    circles = []
    if(not duplicated.empty):
        for index, row in duplicated.iterrows(): 
            lat_mean = row['Latitud']
            lon_mean = row['Longitud']
            circle = dl.Circle(center=[lat_mean, lon_mean], radius=1900)
            circles.append(circle)
        return circles  
    else:
        return []

@app.callback(
    [Output('map', 'children'),
     Output('date-picker', 'date'),
     Output('date-picker', 'disabled_days'),
     Output("grafocuentas","children")],
     
    [Input('upload-data', 'contents'),
     Input('btn-limpiar', 'n_clicks'),
     Input('btn-refresh', 'n_clicks'),
     Input('btn-coincidencias', 'n_clicks')],
    [Input('upload-data', 'filename'),
     Input('date-picker', 'date'),
     Input('hour-slider', 'value')]  
)
def update_output(archivos, n_clicks, nclicksr,coincidencias, nombres_archivos, fecha_elegida, selected_hour):
    map_children = []
    grafo = []
    disabled_days = []
    files_guardados = os.listdir(UPLOAD_DIRECTORY)
    cantidad = len(files_guardados)
    if n_clicks is not None:
        for archivo in files_guardados:
            ruta_completa = os.path.join(UPLOAD_DIRECTORY, archivo)
            os.remove(ruta_completa)
        return [html.Div(f'Actualice la pagina para subir un archivo nuevamente'), None, []]
    if archivos is not None:
        time.sleep(1)
        files_guardados = os.listdir(UPLOAD_DIRECTORY)
        cantidad = len(files_guardados)+1
    if (nclicksr is not None and len(files_guardados) == 0):
        return [html.Div(f'SUBA UN ARCHIVO'), None, []]    
    if cantidad > 0:
        dfs = []
        revisado = True
        circles = []
        markers = []
        fechas_deshabilitadas = []
        fechas_permitidas_dt = []
        polyline_decorator = []
        for idx, name in enumerate(reversed(files_guardados)):
            df = prepare_df(os.path.join(UPLOAD_DIRECTORY, name))
            fechas_permitidas = [str(date) for date in pd.to_datetime(df['Fecha']).dt.date.unique()]
            fechas_permitidas_dt.extend(fechas_permitidas)
        for idx, name in enumerate(reversed(files_guardados)):
                dfs2 = []
                df = prepare_df(os.path.join(UPLOAD_DIRECTORY, name))
                df["file"] = name.split(".")[0]
                first_date = df['Fecha'].min()
                dfs.append(df)
                df_general1 = pd.concat(dfs, ignore_index=True)
                grafo = generar_grafo(df_general1)
                years_range = range(datetime.now().year - 2, datetime.now().year + 1)
                disabled_days = [date.strftime('%Y-%m-%d') for year in years_range for date in (datetime(year, 1, 1) + timedelta(n) for n in range(365)) if date.strftime('%Y-%m-%d') not in fechas_permitidas_dt]
                fechas_deshabilitadas.extend(disabled_days)
                if fecha_elegida is None:
                    fecha_elegida = first_date
                else:
                    fecha_elegida
                if(coincidencias is not None and revisado == True):
                    for name2 in reversed(files_guardados):
                        try:
                            df2 = prepare_df(os.path.join(UPLOAD_DIRECTORY, name2))
                            name2 = name2.split(".")[0]
                            df2["file"] = name2
                            dfs2.append(df2)
                        except Exception as e:
                            print(f"Error al procesar el archivo {name}: {e}")
                    df_general = pd.concat(dfs2, ignore_index=True)
                    circles = encontrar_coincidencias(df_general, fecha_elegida,selected_hour)
                    revisado = False
                markers_part, polyline_decorator_part = create_markers(df, idx,fecha_elegida,selected_hour,name)
                markers += markers_part
                polyline_decorator += polyline_decorator_part
                if df.empty:
                    mensaje = html.Div("No hay datos disponibles para la fecha seleccionada.", style={'color': 'red'})
                    return [dl.Map(id='map', style={'width': '100%', 'height': '70vh'}), fecha_elegida, disabled_days]
                else:
                    map_children.append(
                        dl.Map(
                            [
                                dl.TileLayer(url='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'),
                                *markers,
                                dl.FullScreenControl(),
                                dl.GestureHandling(),
                                polyline_decorator,
                                *circles
                            ],
                            center=(df_general1['Latitud'][0], df_general1['Longitud'][0]),
                            zoom=10,
                            id='map',
                            style={'width': '100%', 'height': '70vh','position': 'absolute', 'zIndex': 1}
                        )
                    )
            
        return [map_children, fecha_elegida, fechas_deshabilitadas,grafo]
    else:
        return [dl.Map(id='map', style={'width': '100%', 'height': '80vh','position': 'absolute', 'zIndex': 1}), None, [],grafo]

def create_markers(df, color_index,fecha_elegida,selected_hour,name):
    markers = []
    color_mapping = {
        0: "naranja",
        1: "rojo",
        2: "azul",
        3: "verde",
        4: "amarillo",
        5: "maps",
        6: "azules",
    }
    df = df[df['Fecha'] == fecha_elegida]
    df['Hora'] = df['Hora'].astype(str)  
    df = df[df['Hora'].str[:2].astype(int) < selected_hour]
    df['Cantidad'] = df.groupby(['Latitud', 'Longitud',"file"]).transform('count')['Fecha']
    df['Cantidad'] = df['Cantidad'].astype(int)
    df = df.drop_duplicates(subset=["Latitud","Longitud","file"])
    polyline_coordinates = [[row['Latitud'], row['Longitud']] for index, row in df.iterrows()]
    polyline = dl.Polyline(positions=polyline_coordinates,color="#ff7800")
    patterns = [dict(offset='0', repeat='10',dash=dict(pixelSize=1))]
    polyline_decorator = dl.PolylineDecorator(children=polyline, patterns=patterns)
    name = name.split(".")[0]
    for index, row in enumerate(df.iterrows()):
        row = row[1]
        color = color_mapping[color_index]  
        marker_id = {'type': 'marker', 'index': f"{color_index}_{index}_{fecha_elegida}_{selected_hour}"}
        marker = dl.Marker(
            position=[row['Latitud'], row['Longitud']],
            id=marker_id, 
            icon = {
                "iconUrl": f'https://facebook.rimgsa.com/marcador{color}.png',
                "iconSize": [30, 40],       # Tamaño del icono
                "shadowSize": [50, 64],     # Tamaño de la sombra
                "iconAnchor": [12, 40],     # Punto del icono que corresponderá a la ubicación del marcador
                "shadowAnchor": [4, 32],    # Lo mismo para la sombra
                "popupAnchor": [-3, -38]    # Punto desde el cual se debe abrir el popup en relación con iconAnchor
            },
            children=[
                dl.Tooltip(html.Div([
                    html.Strong("Numero:"),
                    html.Br(),
                    f"{row['file']}",
                    html.Br(),
                    html.Strong("Destino:"),
                    html.Br(),
                    f"{row['Destino']}",
                    html.Br(),
                    html.Strong("Fecha:"),
                    html.Br(),
                    f"{row['Fecha']}",
                    html.Br(),
                    html.Strong("Hora:"),
                    html.Br(),
                    f"{row['Hora']}",
                    html.Br(),
                    html.Strong("Cantidad de llamadas aquí:"),
                    html.Br(),
                    f"{row['Cantidad']}"
                ])),
            ]
        )
        markers.append(marker)
    return markers,polyline_decorator

@app.callback(
    Output('output-container', 'children'),
    [
        Input({'type': 'marker', 'index': ALL}, 'n_clicks'),
        Input('date-picker', 'date'),
        Input('hour-slider', 'value')
    ],
    [
        State({'type': 'marker', 'index': ALL}, 'position'),
        State({'type': 'marker', 'index': ALL}, 'id')
    ]
)
def marker_click(n_clicks, dia, hora, marker_positions, marker_ids):
    files_guardados = os.listdir(UPLOAD_DIRECTORY)
    if n_clicks:
        latitudes = []
        longitudes = []
        dftotal = []
        dfday = None
        for clicks, position, marker_id in zip(n_clicks, marker_positions, marker_ids):
            if clicks is not None:
                latitudes.append(position[0])
                longitudes.append(position[1])
        for idx, name in enumerate(reversed(files_guardados)):
            df = prepare_df(os.path.join(UPLOAD_DIRECTORY, name))  # Asegúrate de que prepare_df está definido
            df["Origen"] = name.split(".")[0]
            dftotal.append(df)
        dfday = pd.concat(dftotal, ignore_index=True)
        dfday = dfday[dfday['Latitud'].isin(latitudes) & dfday['Longitud'].isin(longitudes)]
        if dia and hora:
            dfday = dfday[dfday['Fecha'] == dia]
            dfday = dfday[dfday['Hora'].str[:2].astype(int) < int(hora)]
            dfday["Nombre"] = ""
        dfday = buscarnombre(dfday,dfday["Destino"].values)
        dfday = dfday[["Origen","Destino","Nombre","Fecha","Hora"]]
        return html.Div([
            dash_table.DataTable(
                id='tabla',
                export_format="csv",
                columns=[{'name': i, 'id': i} for i in dfday.columns],
                style_table={'margin': 'auto', 'width': '100%', "height": "auto"},
                style_cell={'textAlign': 'left', 'maxWidth': '200px', 'whiteSpace': 'normal', 'overflowWrap': 'break-word'},
                style_data_conditional=[
                    {'if': {'row_index': 'odd'}, 'backgroundColor': 'rgb(248, 248, 248)'},
                    {'if': {'column_id': 'Referido'}, 'fontWeight': 'bold'}
                ],
                data=dfday.to_dict('records'),
            )
        ])
    else:
        return []
def buscarnombreunico(numero):
    server = '158.69.26.160'
    port = '49880'
    database = 'ESTADOS'
    username = 'sa'
    password = 'Fac3b00ks'
    
    diccionario_resultados = {}
    if numero:
        query = f"SELECT nombre_completo, num_tel FROM ESTADOS WHERE num_tel LIKE '{numero}'"
        try:
            conexion = pyodbc.connect(
                'DRIVER={ODBC Driver 17 for SQL Server};'
                'SERVER='+server+','+port+';'
                'DATABASE='+database+';UID='+username+';PWD='+password+';'
                'Network Library=DBMSSOCN',
                autocommit=True
            )
        
            cursor = conexion.cursor()
            cursor.execute(query)
            resultados = cursor.fetchall()
            for nombre_completo, num_tel in resultados:
                diccionario_resultados[num_tel] = nombre_completo
            cursor.close()
            conexion.close()
            if diccionario_resultados:
                return diccionario_resultados[numero]
        except pyodbc.Error as e:
            print("Error al conectar a la base de datos:", e)
    return numero

def buscarnombre(dfday, numeros):
    diccionario_resultados = {}
    numeros = set(numeros)
    server = '158.69.26.160'
    port = '49880'
    database = 'ESTADOS'
    username = 'sa'
    password = 'Fac3b00ks'
    if(len(numeros)>0 ):
        
        telefonos = ', '.join([f"'{telefono}'" for telefono in numeros])
        query = f"SELECT nombre_completo, num_tel FROM ESTADOS WHERE num_tel IN ({telefonos})"

        # Establecemos la conexión con la base de datos
        conexion = pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER='+server+','+port+';'
            'DATABASE='+database+';UID='+username+';PWD='+password+';'
            'Network Library=DBMSSOCN',
            autocommit=True
        )
        
        cursor = conexion.cursor()
        cursor.execute(query)
        resultados = cursor.fetchall()
        cursor.close()
        conexion.close()
        for nombre_completo, num_tel in resultados:
            diccionario_resultados[num_tel] = nombre_completo
        dfday["Nombre"] = dfday["Destino"].replace(diccionario_resultados)
    return dfday


@app.callback(
    [Output("llamadas", "children"),
     Output("fig1", "children"),
     Output("nombre_sabana","children"),
     Output("nombrestop10", "children")],
    [Input({"type": "boton", "filename": ALL}, "n_clicks")],
    [State({"type": "boton", "filename": ALL}, "id")]
)
def grafo(n_clicks_list, button_ids_list):
    if any(n_clicks_list):
        ids_presionados = []
        time.sleep(1)
        for button_ids, n_clicks in zip(button_ids_list, n_clicks_list):
            filename = button_ids['filename']
            if n_clicks is not None and pressed_buttons.get(filename, 0) != n_clicks:
                ids_presionados.extend([filename] * n_clicks)
                pressed_buttons[filename] = n_clicks
        time.sleep(2)
        name = ids_presionados[0].split(".")[0]
        df = prepare_df(os.path.join(UPLOAD_DIRECTORY, ids_presionados[0]))
        df = df.fillna("n/a")
        count_destino = df['Destino'].value_counts()
        count_destino_df = pd.DataFrame(count_destino).reset_index()
        count_destino_df.columns = ['Destino', 'Cantidad']
        df = pd.merge(df, count_destino_df, on='Destino')
        df['Cantidad'] = df['Cantidad'].astype(int)
        df = df.drop_duplicates(subset=["Destino"])
        df = df.loc[df["Destino"].str.len() == 10 ]
        df = df[df["Destino"] != name]
        df = df.sort_values("Cantidad", ascending=False)
        df = df.head(10)
        elements = []
        elements.append({'data': {'id': name, 'label': name}})
        imagen = {
            0: "azul.png",
            1: "azulclaro.png",
            2: "azulmarino.png",
            3: "rojo.png",
            4: "transparente.png",
            5: "verde.png"
        }
        for index, row in df.iterrows():
            element = {'data': {'id': str(row["Destino"]), 'label': str(row["Destino"])}}
            elements.append(element)
        for index, row in df.iterrows():
            element = {'data': {'source': name, 'target': str(row["Destino"])}}
            elements.append(element)
        randid = random.randint(0, 5)
        color = imagen[randid]
        df["Nombre"] = "N/A"
        df = buscarnombre(df, df["Destino"].values)
        nombre = buscarnombreunico(name.split(".")[0])
        figbar = graficobarras(df)
        graph_component = dcc.Graph(figure=figbar) 
        cytoscape_graph = cyto.Cytoscape(
            id='cytoscape',
            elements=elements,
            layout={'name': 'cola'},
            style={'width': '100%', 'height': '100%', 'left': 0, 'top': 0},
            stylesheet=[
                {
                    'selector': 'node',
                    'style': {
                        'content': 'data(label)',
                        'background-image': f"assets/{color}",
                        'background-fit': 'cover',
                        'font-size': '10px',  # Tamaño de la fuente
                        'font-weight': 'lighter',
                    }
                },
                {
                    'selector': 'edge',
                    "style": {
                        'label': 'data(label)',
                        "target-arrow-color": "#C5D3E2",
                        "target-arrow-shape": "triangle",
                        "line-color": "#C5D3E2",
                        'arrow-scale': 1,
                        'curve-style': 'bezier'
                    }
                }
            ],
        )

        tabla = html.Div([
            dash_table.DataTable(
                id='tabla',
                export_format="csv",
                columns=[{'name': i, 'id': i} for i in df[["Destino","Nombre","Cantidad"]].columns],
                style_table={'margin': 'auto', 'width': '100%', "height": "auto"},
                style_cell={'textAlign': 'left', 'maxWidth': '200px', 'whiteSpace': 'normal', 'overflowWrap': 'break-word'},
                style_data_conditional=[
                    {'if': {'row_index': 'odd'}, 'backgroundColor': 'rgb(248, 248, 248)'},
                    {'if': {'column_id': 'Referido'}, 'fontWeight': 'bold'}
                ],
                data=df.to_dict('records'),
            )
        ])
        
        return cytoscape_graph,graph_component,f"por {nombre}", tabla
    else:
        return html.Div(), html.Div(),html.Div(), html.Div()

def graficobarras(df):
    top_destinos = df.groupby('Nombre')['Cantidad'].sum().nlargest(10)  # Cambiar 'Nombre' a 'Destino' si se prefiere utilizar el destino
    fig = go.Figure([go.Bar(x=top_destinos.index, y=top_destinos.values, 
                            marker_color='rgb(158,202,225)', 
                            text=top_destinos.index,  # Mostrar el valor de la barra dentro de ella
                            textposition='inside',
                                                        hovertemplate='<b>Cantidad de llamadas: %{y}</b><br><b>Número destino: %{x}</b><extra></extra>')])
    fig.update_layout(title={'text': 'Cantidad de llamadas', 'x': 0.5, 'y': 0.95, 'xanchor': 'center', 'yanchor': 'top'},
                    yaxis_title='Cantidad',
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='black'),
                    bargap=0.15,
                    bargroupgap=0.1)

    fig.update_xaxes(showticklabels=False)

    return fig

app.layout = html.Div([
    dcc.Location(id='url', refresh=False),  
    dcc.Upload(
        id="upload-data",
        children=html.Div(["Seleccionar una sabana telefonica"]),
        style={"width": "100%", "height": "60px", "lineHeight": "60px","borderWidth": "1px","borderStyle": "dashed","borderRadius": "5px","textAlign": "center","margin": "10px",
        },
        multiple=True,
    ),
    html.Div(
        id='file-list-container',
        children=[
            html.Ul(id="file-list", style={"list-style-type": "none", "padding": 0}),
        ],
        style={"max-width": "200px", "max-height": "200px", "overflow": "auto", "float": "right", "margin-right": "10px","display": "none"}
    ),
    html.Button('Borrar Archivos', id='btn-limpiar', style={"margin": "10px", "background-color": "#f44336","color": "white", "font-size": "16px", "padding": "10px 24px"}),
    dcc.DatePickerSingle(
        id='date-picker',
        display_format='YYYY-MM-DD',
        with_portal=True,
        style={'display': 'inline-block', 'margin-right': '10px','color': 'black', 'border-radius': '50px', 'padding': '5px 10px',
        }
    ),
    html.Button('Identificar coincidencias', 
                    id='btn-coincidencias', 
                    style={"margin": "10px","background-color": "#4CAF50", "color": "white", "font-size": "16px", "padding": "10px 24px"}),
    html.Button('Actualizar', 
                    id='btn-refresh', 
                    style={"margin": "10px", "background-color": "#3d85c6", "color": "white", "font-size": "16px","padding": "10px 24px"}),
    dcc.Slider(
        id='hour-slider',
        min=0,
        max=24,
        step=1,
        marks={i: f'{i}:00' for i in range(0, 25)},
        value=15
    ),
    html.Div(
        children=[
            dl.Map(id='map', style={'width': '70%',"margin-right":"2%", 'height': '70vh'}),
            html.Div(id='output-container',style={'width': '40%',"height": "70vh","maxheight": '70vh',"overflow": "auto"}),
        ],
        style={'display': 'flex'}
    ),
    #cierra primer cuadro de visualizacion
    html.Br(),
    #Abre segundo cuadro de visualizacion
    html.Div(
        id="opciones",
        style={"width": "100%", "height": "100px", "display": "flex", "justify-content": "center", "align-items": "center", "overflow": "auto"
        }
    ),
    html.Div(
    children=[
        html.Div( 
            children=[
                html.H1("Top 10 números marcados", style={"text-align": "center", "font-family": "Arial, sans-serif", "font-weight": "normal", "font-size": "1.5em", "margin-bottom": "20px"}),
                html.Div(id="llamadas", style={"width": "100%", "height": "100%"}),
            ],
            style={
                "width": "33%",
                "height": "60vh",
                "maxHeight": "60vh",
                "display": "flex",
                "flex-direction": "column",
            }
        ),
        html.Div(
            children=[
                html.H1("Top 10 números marcados", style={"text-align": "center", "font-family": "Arial, sans-serif", "font-weight": "normal", "font-size": "1.5em"}),
                html.Div(id="nombre_sabana", style={"text-align": "center", "font-family": "Arial, sans-serif", "font-weight": "normal", "font-size": "1.5em"}),
                html.Div(id="nombrestop10", style={"width":"100%"}),
            ],
            style={
                "width": "25%",
                "height": "60vh",
                "maxHeight": "60vh",
                "overflow": "auto",
                "margin-right": "5%"
               # "background-color": "lightblue",
            }
        ),
        html.Div(
            children=[
                html.Div(id="fig1", style={"width": "100%", "height": "70vh"}),
            ],
            style={
                "width": "33%",
                "height": "70vh",
                "maxHeight": "70vh",
                "overflow": "auto",
               #"background-color": "lightblue",
                "display": "flex",
                "flex-direction": "column",
                "justify-content": "center",
                "align-items": "center"
            }
        )
    ],
    style={"display": "flex"}
),
    html.Div(
        children=[
            html.H1("Conexiones de llamadas entre sabanas", style={"text-align": "center", "font-family": "Arial, sans-serif", "font-weight": "normal", "font-size": "1.5em"}),
            html.Div(id="grafocuentas", style={"width": "50%", "height": "800px", "margin": "0 auto"})
        ], style={"width": "100%", "height": "800px"}
    )
])
def generar_grafo(df):
    print(df.head())
    
    elements = []
    df["Origen"] = df["file"]
    df["Destino"] = df["Destino"].str.strip()
    df = df[df["Destino"].str.len() == 10]
    df = df.drop_duplicates(subset=["Origen","Destino"])
    for name in df["Origen"].unique():
        elements.append({'data': {'id': name, 'label': name}})
    df = df[df.groupby("Destino")["Origen"].transform("count") > 1]
    if df.empty:
        return html.Div()
    else:
        df = buscarnombre(df, df["Destino"].values)
        for index, row in df.iterrows():
            element = {'data': {'id': str(row["Destino"]), 'label': str(row["Nombre"])}}
            elements.append(element)
        for index, row in df.iterrows():
            if(str(row["Origen"]) != str(row["Destino"])):
                element = {'data': {'source': str(row["Origen"]), 'target': str(row["Destino"])}}
                elements.append(element)
        cytoscape_graphall = cyto.Cytoscape(
                id='cytoscape',
                elements=elements,
                layout={'name': 'cola'},
                style={'width': '100%', 'height': '100%', 'left': 0, 'top': 0},
                stylesheet=[
                    {
                        'selector': 'node',
                        'style': {
                            'content': 'data(label)',
                            #'background-image': f"assets/{color}",
                            'background-fit': 'cover',
                            'font-size': '10px', 
                            'font-weight': 'lighter',
                            'autoungrabify': 'true'
                        }
                    },
                    {
                        'selector': 'edge',
                        "style": {
                            'label': 'data(label)',
                            "target-arrow-color": "#C5D3E2",
                            "target-arrow-shape": "triangle",
                            "line-color": "#C5D3E2",
                            'arrow-scale': 1,
                            'curve-style': 'bezier'
                        }
                    }
                ],
            )
        return cytoscape_graphall
if __name__ == '__main__':
    app.run_server(debug=True)