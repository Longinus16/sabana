import base64
from urllib.parse import quote as urlquote
from flask import Flask, send_from_directory
import dash
import dash_leaflet as dl
from dash import callback_context
from dash import dcc, html, Input, Output, State
import os
import re
import dash_leaflet.express as dlx
from datetime import datetime, timedelta
import io
import pandas as pd
import numpy as np
import colorsys

directorio_actual = os.getcwd()

nombre_directorio = "app_uploaded_files"

UPLOAD_DIRECTORY = os.path.join(directorio_actual, nombre_directorio)
if not os.path.exists(UPLOAD_DIRECTORY):
    os.makedirs(UPLOAD_DIRECTORY)

def get_unique_color(index, total_files):
    hue = index / total_files
    rgb = colorsys.hsv_to_rgb(hue, 0.8, 0.8)
    color = "#{:02x}{:02x}{:02x}".format(
        int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)
    )
    return color

def dms_to_decimal(dms):
    if isinstance(dms, float):
        return dms
    else:
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
    columnas = ["Fecha", "Hora","Latitud","Longitud"]
    path = f'{path}'
    if "csv" in path:
        sabana = pd.read_csv(path)
    elif "xlsx" in path:
        print(path)
        sabana = pd.read_excel(path)
        print(sabana.head())
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
        if "ubicacion geografica (latitud / longitud)" == column:
            sabana['Latitud'] = sabana.iloc[:,idx]
            sabana['Longitud'] = sabana.iloc[:,idx+1]
            sabana['Latitud'] = sabana['Latitud'].apply(dms_to_decimal)
            sabana['Longitud'] = sabana['Longitud'].apply(dms_to_decimal)
            
    formato = sabana.at[0, 'Fecha']
    if "-" in formato:
        formato = '%Y-%m-%d'
        
    if "/" in formato:
        formato = '%d/%m/%Y'

        
    print(formato)
    sabana['Fecha'] = pd.to_datetime(sabana['Fecha'], format=formato, errors='coerce')
    sabana = sabana.drop_duplicates(subset=columnas)
    sabana = sabana.dropna(subset=["Latitud","Longitud"])
    print(sabana.head())
    return sabana[columnas]

server = Flask(__name__)
app = dash.Dash(server=server)

@server.route("/download/<path:path>")
def download(path):
    """Serve a file from the upload directory."""
    return send_from_directory(UPLOAD_DIRECTORY, path, as_attachment=True)

app.layout = html.Div([
    dcc.Location(id='url', refresh=False),  
    dcc.Upload(
        id="upload-data",
        children=html.Div(["Seleccionar una sabana telefonica"]),
        style={
            "width": "100%",
            "height": "60px",
            "lineHeight": "60px",
            "borderWidth": "1px",
            "borderStyle": "dashed",
            "borderRadius": "5px",
            "textAlign": "center",
            "margin": "10px",
        },
        multiple=True,
    ),
    html.Div(
        id='file-list-container',
        children=[
            html.Ul(id="file-list", style={"list-style-type": "none", "padding": 0}),
        ],
        style={"max-width": "500px", "float": "right", "margin-right": "10px"}
    ),
    html.Button('Borrar Archivos', id='btn-limpiar', style={"margin": "10px"}),
    dcc.DatePickerSingle(
            id='date-picker',
            display_format='YYYY-MM-DD',
            with_portal=True
    ),
    dcc.Slider(
        id='hour-slider',
        min=0,
        max=24,
        step=1,
        marks={i: f'{i}:00' for i in range(0, 25)},
        value=12  # Puedes establecer un valor predeterminado según tus necesidades
    ),
    html.Div(id='selected-date-output', style={"margin": "10px"}),
    dl.Map(id='map', style={'width': '100%', 'height': '70vh'}),
])


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
    Output("file-list", "children"),
    [Input("upload-data", "filename"),
     Input('btn-limpiar', 'n_clicks'),
     Input("upload-data", "contents")],
    [State('file-list', 'children')]
)
def update_output(uploaded_filenames, n_clicks, uploaded_file_contents, current_children):
    if n_clicks is not None:
        return [html.Li("Archivo borrado")]

    if uploaded_filenames is not None and uploaded_file_contents is not None:
        for name, data in zip(uploaded_filenames, uploaded_file_contents):
            save_file(name, data)
            
    files = uploaded_files()
    if len(files) == 0:
        return [html.Li("Sin archivo!")]
    else:
        return [html.Li(file_download_link(filename)) for filename in files]
    
@app.callback(
    [Output('map', 'children'),
    Output('date-picker','date'),
    Output('date-picker', 'disabled_days')],
    [Input('upload-data', 'contents'),
     Input('btn-limpiar', 'n_clicks')],
    [Input('upload-data', 'filename'),
     Input('date-picker', 'date'),
     Input('hour-slider', 'value')]  
)
def update_output(archivos, n_clicks, nombres_archivos, fecha_elegida, selected_hour):
    
    children = []
    map_children = []
    disabled_days = []

    if n_clicks is not None:
        archivos_a_borrar = os.listdir(UPLOAD_DIRECTORY)
        for archivo in archivos_a_borrar:
            ruta_completa = os.path.join(UPLOAD_DIRECTORY, archivo)
            os.remove(ruta_completa)
        return [html.Div(f'Actualice la pagina para subir un archivo nuevamente'),None,[]]

    elif archivos is not None:
        for name, data in zip(nombres_archivos, archivos):
            save_file(name, data)
        files = uploaded_files()
        for archivo in files:
            df = prepare_df(os.path.join(UPLOAD_DIRECTORY, archivo))
            first_date = df['Fecha'].min()
            fechas_permitidas_dt = [str(date) for date in pd.to_datetime(df['Fecha']).dt.date.unique()]
            years_range = range(datetime.now().year - 1, datetime.now().year + 1)
            disabled_days = [date.strftime('%Y-%m-%d') for year in years_range for date in (datetime(year, 1, 1) + timedelta(n) for n in range(365)) if date.strftime('%Y-%m-%d') not in fechas_permitidas_dt]
            print(df.head())
            if fecha_elegida is None:
                fecha_elegida = first_date
            else:
                fecha_elegida
            df = df[df['Fecha'] == fecha_elegida]
            df['Hora'] = df['Hora'].astype(str)  
            df = df[df['Hora'].str[:2].astype(int) < selected_hour]
            df['Cantidad'] = df.groupby(['Latitud', 'Longitud']).transform('count')['Fecha']
            df['Cantidad'] = df['Cantidad'].astype(int)
            if df.empty:
                mensaje = html.Div("No hay datos disponibles para la fecha seleccionada.", style={'color': 'red'})
                return [dl.Map(id='map', style={'width': '100%', 'height': '70vh'}), fecha_elegida, disabled_days]
            else:
                df = df.drop_duplicates(subset=["Latitud","Longitud"])
                polyline_coordinates = [[row['Latitud'], row['Longitud']] for index, row in df.iterrows()]
                polyline = dl.Polyline(positions=polyline_coordinates,color="#ff7800")
                patterns = [dict(offset='0', repeat='10',dash=dict(pixelSize=1))]
                polyline_decorator = dl.PolylineDecorator(children=polyline, patterns=patterns)
                                                    
                markers = [
                    dl.Marker(
                        position=[row['Latitud'], row['Longitud']],
                        children=[
                            dl.Tooltip(html.Div([
                                html.Strong("Fecha:"),
                                html.Br(),
                                f"{row['Fecha']}",
                                html.Br(),
                                html.Strong("Hora:"),
                                html.Br(),
                                f"{row['Hora']}",
                                html.Br(),
                                html.Strong("Cantidad de llamadas aqui:"),
                                html.Br(),
                                f"{row['Cantidad']}"
                            ])),
                            dl.CircleMarker(
                                center=(row['Latitud'], row['Longitud']),
                                radius=4,
                                color="#008000" if index in [0, len(df) - 1] else "blue",  # Primer y último en naranja, otros en azul
                                fillColor="#ff7800" if index in [0, len(df) - 1] else "blue",
                                fillOpacity=1,
                            )
                        ]
                    )
                    for index, row in df.iterrows()
                ]
                map_children = [
                    dl.Map(
                        [
                            dl.TileLayer(url='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'),
                            *markers,
                            dl.FullScreenControl(),
                            polyline_decorator
                            
                        ],
                        center=(df['Latitud'].mean(), df['Longitud'].mean()),
                        zoom=10,
                        id='map',
                        style={'width': '100%', 'height': '70vh','position': 'absolute', 'zIndex': 1}
                    )
                ]
                children.append(html.Li(file_download_link(archivo)))

        return [map_children, fecha_elegida,disabled_days]

    else:
        return [dl.Map(id='map', style={'width': '100%', 'height': '80vh','position': 'absolute', 'zIndex': 1}), None,[]]

if __name__ == '__main__':
    app.run_server(debug=True)