""" Page for the monitoring of query performance characteristics. """
# Plotly
import plotly.graph_objs as go
# Dash
import dash_table as dt
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output
# DashEngine
from dashengine.dashapp import dashapp
import dashengine.bigquery as bigquery

# Route for profiling page
ROUTE = "/profile"
# Name used when linking, for example in the navigation bar
LINKNAME = "Profiling"
# Title for rendering in the navbar
TITLE = "Cached Query Profiler"


# Helper functions #################################################

def __fetch_query_from_uuid(uuid: str) -> bigquery.BigQueryResult:
    """ Fetches a cached BigQuery result from its UUID.

        Args:
            uuid (str): The UUID of the query to be retrieved.

        Returns:
            (BigQueryResult): The corresponding BigQuery result object.
    """
    # Fetch cached queries
    queries = bigquery.fetch_cached_queries()
    selected_query = None
    for query in queries:
        if query.uuid == uuid:
            selected_query = query
    if selected_query is None:
        raise RuntimeError(f"Cannot find query with UUID {uuid}")
    return selected_query


def __index_query(query, key: str) -> float:
    """ Returns a property of the query class, keyed by a string.
        The key must be one of:
            ['Memory', 'Duration', 'Bytes Processed', 'Bytes Billed']

        Args:
            query (BigQueryResult): A BigQuery result class
            key (string): A key of the BigQueryResult object

        Returns:
            (float): The value in `query` corresponding to the key.
    """
    ResultDict = {"Memory": query.memory_usage(),
                  "Duration": query.duration,
                  "Bytes Processed": query.bytes_processed,
                  "Bytes Billed": query.bytes_billed}
    return ResultDict[key]


def __normalising_constants(cached_queries: list):
    """ Computes totals over the full set of cached queries to normalise the summary chart. """
    totals = {'Memory': 0.0, 'Duration': 0.0, 'Bytes Processed': 0.0, 'Bytes Billed': 0.0}
    for query in cached_queries:
        for key in totals:
            totals[key] += __index_query(query, key)
    # Avoid dividing by zero
    for key in totals:
        if totals[key] == 0:
            totals[key] = 1
    return totals


# Dash callbacks #################################################

def _query_profile_charts(query: bigquery.BigQueryResult,
                          totals: dict) -> go.Bar:
    """ Generates a set of bar charts for a single query. """
    yvals = ['Memory', 'Duration', 'Bytes Processed', 'Bytes Billed']
    return go.Bar(y=yvals,
                  x=[ 100.0 * __index_query(query, key) / totals[key] for key in yvals],
                  name=query.uuid,
                  orientation='h')


def _query_profile_table(cached_queries: list) -> dt.DataTable:
    """ Generates a table profiling all cached queries. """
    __normalising_constants(cached_queries)
    # Setup all data for the table
    data = [{"ID": query.source.query_id,
             "UUID": query.uuid,
             "Duration": query.duration,
             "Memory Usage": query.memory_usage(),
             "Bytes Processed": query.bytes_processed,
             "Bytes Billed": query.bytes_billed} for query in cached_queries]
    # Build list of columns from the data keys
    columns = [ {"name": i, "id": i} for i in data[0]]
    # Build datatable
    return dt.DataTable(id='query-profile-table', columns=columns, data=data,
                        sorting=True, sorting_type="single", row_selectable="single",
                        style_header={
                            'backgroundColor': 'white',
                            'fontWeight': 'bold'
                        },
                        style_cell_conditional=[
                            {
                                'if': {'column_id': c},
                                'textAlign': 'left'
                            } for c in ['ID', 'UUID']
                        ],
                        style_as_list_view=True)


@dashapp.callback(
    Output('query-profile-body', 'children'),
    [Input('query-profile-table', 'derived_virtual_data'),
     Input('query-profile-table', 'derived_virtual_selected_rows')])
def _query_profile_body(rows, selected_row_indices) -> dcc.Markdown:
    """ Returns the formatted SQL body of the selected query. """
    selected_UUID = rows[selected_row_indices[0]]["UUID"]
    selected_query = __fetch_query_from_uuid(selected_UUID)

    # Build query body in markdown code block
    query_code = " ``` \n " + selected_query.source.body + " \n ```"
    return dcc.Markdown(query_code)


@dashapp.callback(
    Output('query-profile-parameters', 'children'),
    [Input('query-profile-table', 'derived_virtual_data'),
     Input('query-profile-table', 'derived_virtual_selected_rows')])
def _query_profile_parameters(rows, selected_row_indices):
    """ Returns the parameters of the selected query. """
    selected_UUID = rows[selected_row_indices[0]]["UUID"]
    selected_query = __fetch_query_from_uuid(selected_UUID)
    parameters = selected_query.parameters
    if len(parameters) == 0:
        return html.H6("No parameters")
    # Build a table consisting of query parameters
    columns = [{"name": "Parameter", "id": "Parameter"},
               {"name": "Value", "id": "Value"}]
    parameter_data = [{"Parameter": key, "Value": str(value)}
                      for key, value in parameters.items()]
    return dt.DataTable(id='query-profile-parameter-table',
                        columns=columns,
                        data=parameter_data,
                        style_table={"margin-bottom": "30px"},
                        style_cell={
                            'minWidth': '0px', 'maxWidth': '180px',
                            'whiteSpace': 'normal'
                        })


@dashapp.callback(
    Output('query-profile-details', 'children'),
    [Input('query-profile-table', 'derived_virtual_data'),
     Input('query-profile-table', 'derived_virtual_selected_rows')])
def _query_profile_details(rows, selected_row_indices) -> list:
    """ Returns the details (SQL and parameters) of the selected query. """
    if rows is None or len(selected_row_indices) != 1:
        return [html.H5("Select a query to view details",
                        style={"textAlign": "center", "margin-top": "30px"})]
    return [ html.H3("Query Details",
                     style={"textAlign": "center", "margin-top": "30px"}),
             html.H4("Query Body",
                     style={"textAlign": "left", "margin-top": "0px"}),
             html.Div(id="query-profile-body"),
             html.H4("Query Parameters",
                     style={"textAlign": "left", "margin-top": "0px"}),
             html.Div(id="query-profile-parameters")]


# Layout #################################################################

def layout() -> html.Div:
    """ Generates the layout for the query profiling page. """
    # Compute performance metrics
    queries = bigquery.fetch_cached_queries()

    # No queries cached
    if len(queries) == 0:
        return html.H4("No queries in cache",
                       style={"textAlign": "center", "margin-top": "30px"})

    totals = __normalising_constants(queries)
    bar_charts = [_query_profile_charts(query, totals) for query in queries]
    layout = go.Layout(barmode='stack')
    profile_figure = go.Figure(data=bar_charts, layout=layout)

    return html.Div(className="container", children=[
        dcc.Graph(figure=profile_figure),
        _query_profile_table(queries),
        html.Div(id="query-profile-details")
    ])
