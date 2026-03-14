"""
HVP Dashboard - Production Ready Implementation
Enhanced Dash application for portfolio cashflow engine analysis
"""

import io
import re
import dash
from dash import dcc, html, Input, Output, State, callback, dash_table
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from snowflake_session import session

# ============================================================================
# Configuration
# ============================================================================

METRIC_TITLES = {
	'bom_principalbalance':        'BOM Total Principal Balance',
	'totalprincipalbalance':       'Total Principal Balance',
	'grosscash':                   'Gross Cash',
	'ScheduledPaymentAmountR':     'Scheduled Payment Rate',
	'PPMT Rate':                   'Principal Payment Rate',
	'IPMT Rate':                   'Interest Payment Rate',
	'CDR':                         'CDR',
	'MPR':                         'vSMM (Full Prepay Rate)',
	'MCR':                         'MCR',
	'MDR':                         'MDR',
	'CPR':                         'CPR (Total Prepay Rate)',
	'MTPR':                        'MPR',
	'scheduledpaymentamount':      'Scheduled Payment',
	'contractualprincipalpayment': 'Contractual Principal Payment',
	'interestpayment':             'Interest Payment',
	'principaltotalprepayment':    'Principal Total Prepayment',
	'principalfullprepayment':     'Principal Full Prepayment',
	'principalpartialprepayment':  'Principal Partial Prepayment',
	'chargeoffamount':             'Charge Off Amount',
	'CCDR':                        'Cumulative Charge Off',
	'postchargeoffcollections':    'Recovery',
	'PostChargeOffCollectionR':    'Recovery Rate',
	'CumRecoveryR':                'Cumulative Recovery Rate',
	'GrossCashR':                  'Gross Cash Rate',
}

TAB_CATEGORIES = {
	'Balance': ['bom_principalbalance', 'totalprincipalbalance'],
	'Payment': ['contractualprincipalpayment', 'PPMT Rate', 'interestpayment', 'IPMT Rate'],
	'Prepayment': ['principalfullprepayment', 'principalpartialprepayment', 'MPR', 'MCR', 'principaltotalprepayment'],
	'Default': ['chargeoffamount', 'CDR', 'MDR'],
	'Other': ['postchargeoffcollections', 'grosscash']
}

TOTAL_METRICS = [
	'bom_principalbalance', 'totalprincipalbalance', 'scheduledpaymentamount',
	'contractualprincipalpayment', 'interestpayment', 'principalfullprepayment',
	'CPR', 'principalpartialprepayment', 'principaltotalprepayment',
	'chargeoffamount', 'CDR', 'postchargeoffcollections', 'grosscash'
]

PERCENT_METRICS = ['PPMT Rate', 'IPMT Rate', 'MPR', 'CPR', 'MCR', 'MTPR', 'MDR', 'CDR',
	'ScheduledPaymentAmountR', 'PostChargeOffCollectionR', 'GrossCashR'
]

SCENARIO_COLORS = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3', '#FF6692']
MAX_SCENARIOS = 7

# 23 charts, 3-column grid (8 rows, last row has 2)
CHART_CONFIG = [
	('bom_principalbalance',        'dollar'),   # row 1 — balances & cash
	('totalprincipalbalance',       'dollar'),
	('grosscash',                   'dollar'),
	('ScheduledPaymentAmountR',     'percent'),  # row 2 — payment rates
	('PPMT Rate',                   'percent'),
	('IPMT Rate',                   'percent'),
	('CDR',                         'percent'),  # row 3 — default & prepay rates (annual)
	('MPR',                         'percent'),  # vSMM
	('MCR',                         'percent'),
	('MDR',                         'percent'),  # row 4 — default & prepay rates (monthly)
	('CPR',                         'percent'),
	('MTPR',                        'percent'),  # MPR
	('scheduledpaymentamount',      'dollar'),   # row 5 — payment amounts
	('contractualprincipalpayment', 'dollar'),
	('interestpayment',             'dollar'),
	('principaltotalprepayment',    'dollar'),   # row 6 — prepayment amounts
	('principalfullprepayment',     'dollar'),
	('principalpartialprepayment',  'dollar'),
	('chargeoffamount',             'dollar'),   # row 7 — default amounts
	('CCDR',                        'percent'),
	('postchargeoffcollections',    'dollar'),   # row 8 — recovery
	('PostChargeOffCollectionR',    'percent'),
	('CumRecoveryR',                'percent'),
]

# ============================================================================
# Snowflake Functions
# ============================================================================

def get_cutoff_dates():
	"""Retrieve available cutoff dates"""
	dates_df = session.sql('''
		SELECT DISTINCT cutoff_dt
		FROM cashflow_engine.fra_pcfe.model_scenario
		ORDER BY cutoff_dt DESC
	''').to_pandas()

	if dates_df.empty:
		return []

	dates = []
	for d in dates_df['CUTOFF_DT'].tolist():
		if d is None or (isinstance(d, float) and pd.isna(d)):
			continue
		date_str = str(d).strip()
		if date_str and date_str.lower() != 'nan':
			dates.append(date_str)

	unique_dates = list(set(dates))
	return sorted(unique_dates, reverse=True)

def get_model_names(date_select):
	"""Retrieve model names for selected date"""

	names_df = session.sql(f'''
		SELECT DISTINCT model_name
		FROM cashflow_engine.fra_pcfe.model m
		LEFT JOIN cashflow_engine.fra_pcfe.model_scenario s ON s.model_key = m.model_key
		WHERE s.cutoff_dt = '{date_select}'
		ORDER BY model_name
	''').to_pandas()
	return sorted(names_df['MODEL_NAME'].tolist()) if not names_df.empty else []

def get_hierarchy(date_select):
	"""Return PORTFOLIO / BATCHNAME hierarchy for a given date + model."""
	df = session.sql(f'''
		SELECT DISTINCT
			m.model_name,
			CASE WHEN fp.portfolioalias = 'Helen' THEN b.dealname
				 ELSE fp.portfolioalias END AS portfolio,
			b.batchname
		FROM cashflow_engine.fra_pcfe.output_scenario_cashflow cf
		LEFT JOIN datamart.it.batch b                        ON b.batchid         = cf.batchid
		LEFT JOIN datamart.finance.financeportfolio fp       ON b.accountingcodeid = fp.portfoliocode
		LEFT JOIN cashflow_engine.fra_pcfe.model_scenario s  ON cf.scenario_key   = s.scenario_key
		LEFT JOIN cashflow_engine.fra_pcfe.model m           ON s.model_key       = m.model_key
		WHERE s.cutoff_dt = '{date_select}'
		ORDER BY portfolio, batchname
	''').to_pandas()
	df.columns = [c.upper() for c in df.columns]
	return df

def fetch_data(date_select, model_name, batch_names):
	"""Fetch raw data from snowflake"""

	batches_string = ", ".join([f"'{b}'" for b in batch_names])

	batch_df = session.sql(f'''
		SELECT DISTINCT batchid
		FROM datamart.it.batch
		WHERE batchname IN ({batches_string})
	''').to_pandas()

	batch_ids = batch_df['BATCHID'].tolist()
	batch_num_str = ", ".join(f"{x}" for x in batch_ids)

	data_raw = session.sql(f'''
		SELECT
			cf.batchid,
			cf.asofdate,
			cf.metric,
			cf.value,
			COALESCE(s.scenario_name, TO_VARCHAR(cf.scenario_key)) AS scenario_name,
			cf.run_id
		FROM cashflow_engine.fra_pcfe.model_scenario s
		LEFT JOIN cashflow_engine.fra_pcfe.model m ON s.model_key = m.model_key
		LEFT JOIN cashflow_engine.fra_pcfe.output_scenario_cashflow cf ON s.scenario_key = cf.scenario_key
		LEFT JOIN datamart.it.batch b ON cf.batchid = b.batchid
		WHERE s.cutoff_dt = '{date_select}'
			AND m.model_name = '{model_name}'
			AND b.batchid IN ({batch_num_str})
		QUALIFY ROW_NUMBER() OVER (
			PARTITION BY s.model_key, s.uw_key, s.scenario_name, cf.asofdate, cf.metric, cf.batchid
			ORDER BY s.seq_nbr DESC, cf.run_id ASC
		) = 1
	''').to_pandas()

	return data_raw.rename(columns=lambda x: x.upper())

def calculate_columns(df):
	"""Calculate derived metrics"""
	batch_flag = 'BATCHID' in df.columns

	if batch_flag:
		df = df.pivot(
			index=['RUN_ID', 'SCENARIO_NAME', 'ASOFDATE', 'BATCHID'],
			columns='METRIC', values='VALUE'
		).reset_index()
	else:
		df = df.pivot(
			index=['RUN_ID', 'SCENARIO_NAME', 'ASOFDATE'],
			columns='METRIC', values='VALUE'
		).reset_index()

	def col(name):
		"""Return column if it exists, else a zero Series."""
		return df[name].fillna(0) if name in df.columns else pd.Series(0, index=df.index)

	bom = col('totalprincipalbalance')
	df['PPMT Rate'] = (col('contractualprincipalpayment') / bom).fillna(0)
	df['IPMT Rate'] = (col('interestpayment') / bom).fillna(0)
	df['MPR'] = (col('principalfullprepayment') / bom).fillna(0)
	df['MCR'] = (col('principalpartialprepayment') / bom).fillna(0)
	df['CPR'] = (1 - (1 - (col('principaltotalprepayment') / bom).fillna(0)) ** 12)
	df['CDR'] = (1 - (1 - (col('chargeoffamount') / bom).fillna(0)) ** 12)
	df['MDR'] = (col('chargeoffamount') / bom).fillna(0)
	df['ScheduledPaymentAmountR'] = (col('scheduledpaymentamount') / bom).fillna(0)
	df['MTPR'] = (col('principaltotalprepayment') / bom).fillna(0)
	df['PostChargeOffCollectionR'] = (col('postchargeoffcollections') / bom).fillna(0)
	df['GrossCashR'] = (col('grosscash') / bom).fillna(0)

	if batch_flag:
		df = df.melt(
			id_vars=['RUN_ID', 'SCENARIO_NAME', 'ASOFDATE', 'BATCHID'],
			var_name='METRIC', value_name='VALUE'
		)
	else:
		df = df.melt(
			id_vars=['RUN_ID', 'SCENARIO_NAME', 'ASOFDATE'],
			var_name='METRIC', value_name='VALUE'
		)

	return df

# ============================================================================
# Dash App
# ============================================================================

app = dash.Dash(
	__name__,
	external_stylesheets=[dbc.themes.SANDSTONE],
	suppress_callback_exceptions=True
)
app.title = "HVP Dashboard"
server = app.server   # Gunicorn entry point: gunicorn app:server

# ============================================================================
# Layout
# ============================================================================

app.layout = dbc.Container([
	dcc.Store(id='table-store'),
	dcc.Store(id='horizon-store', data=5),
	dcc.Store(id='hierarchy-store'),
	dcc.Download(id='download-csv'),

	dbc.Row([

		# ── Left sidebar ──────────────────────────────────────────────
		dbc.Col([
			html.H4("HVP Dashboard", className="fw-bold mt-4 mb-0"),
			html.P("Portfolio Cashflow Engine Analysis", className="text-muted small mb-4"),

			dbc.Label("Cutoff Date", className="fw-bold small"),
			dcc.Dropdown(
				id='date-select', placeholder='Select date...',
				clearable=False, className="mb-3"
			),

			dbc.Label("Model Name", className="fw-bold small"),
			dcc.Dropdown(
				id='model-select', placeholder='Select model...',
				clearable=False, className="mb-3"
			),

			dbc.Label("Portfolio", className="fw-bold small"),
			dbc.ButtonGroup([
				dbc.Button("All",  id='portfolio-all',  n_clicks=0, size='sm', outline=True, color='secondary'),
				dbc.Button("None", id='portfolio-none', n_clicks=0, size='sm', outline=True, color='secondary'),
			], className="mb-2 w-100"),
			html.Div(
				dbc.Checklist(id='portfolio-select', options=[], value=[], input_class_name="me-2"),
				style={'overflowY': 'auto', 'maxHeight': '20vh', 'border': '1px solid #dee2e6',
					   'borderRadius': '4px', 'padding': '8px', 'marginBottom': '16px'}
			),

			dbc.Label("Batches", className="fw-bold small"),
			dbc.ButtonGroup([
				dbc.Button("All",  id='batch-all',  n_clicks=0, size='sm', outline=True, color='secondary'),
				dbc.Button("None", id='batch-none', n_clicks=0, size='sm', outline=True, color='secondary'),
			], className="mb-2 w-100"),
			html.Div(
				dbc.Checklist(id='batch-select', options=[], value=[], input_class_name="me-2"),
				style={'overflowY': 'auto', 'maxHeight': '20vh', 'border': '1px solid #dee2e6',
					   'borderRadius': '4px', 'padding': '8px', 'marginBottom': '16px'}
			),

			dbc.Label("Scenarios", className="fw-bold small"),
			dbc.ButtonGroup([
				dbc.Button("All",   id='scenario-all',   n_clicks=0, size='sm', outline=True, color='secondary'),
				dbc.Button("None",  id='scenario-none',  n_clicks=0, size='sm', outline=True, color='secondary'),
				dbc.Button("Up",    id='scenario-up',    n_clicks=0, size='sm', outline=True, color='info'),
				dbc.Button("Down",  id='scenario-down',  n_clicks=0, size='sm', outline=True, color='info'),
				dbc.Button("Other", id='scenario-other', n_clicks=0, size='sm', outline=True, color='info'),
			], className="mb-2 w-100"),
			html.Div(
				dbc.Checklist(id='scenario-select', options=[], value=[], input_class_name="me-2"),
				style={'overflowY': 'auto', 'maxHeight': '25vh', 'border': '1px solid #dee2e6',
					   'borderRadius': '4px', 'padding': '8px', 'marginBottom': '4px'}
			),
			html.Div(id='scenario-warning', className="mb-2"),

			dbc.Button(
				"Fetch & Process Data",
				id='generate-button', n_clicks=0,
				className='w-100 mb-2', disabled=True
			),
			dbc.Button(
				"Download CSV",
				id='download-button', color='success', outline=True,
				size='sm', className='w-100', style={'display': 'none'}
			),

			html.Div(id='fetch-status', className="mt-2"),

		], width=2, className="border-end pe-3", style={
			'position': 'sticky', 'top': 0,
			'height': '100vh', 'overflowY': 'auto',
			'overflowX': 'hidden'
		}),

		# ── Right content ─────────────────────────────────────────────
		dbc.Col([

			# Summary tables (hidden until data loaded)
			html.Div(id='summary-section', style={'display': 'none'}, children=[
				html.H5("Summary Tables", className="fw-bold mt-3 mb-2"),

				html.P("1. DTD — Trailing 12-mo", className="fw-semibold small text-muted mb-1"),
				dash_table.DataTable(id='dtd-table', page_size=20,
					style_table={'overflowX': 'auto', 'marginBottom': '16px'},
					style_header={'backgroundColor': '#343a40', 'color': 'white', 'fontWeight': 'bold', 'fontSize': '11px'},
					style_cell={'fontSize': '11px', 'padding': '4px 8px', 'textAlign': 'right'},
					style_cell_conditional=[{'if': {'column_id': 'Scenario'}, 'textAlign': 'left'}],
					style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#f8f9fa'}],
				),

				html.P("2. Projected — Forward 12-mo", className="fw-semibold small text-muted mb-1"),
				dash_table.DataTable(id='projected-table', page_size=20,
					style_table={'overflowX': 'auto', 'marginBottom': '16px'},
					style_header={'backgroundColor': '#343a40', 'color': 'white', 'fontWeight': 'bold', 'fontSize': '11px'},
					style_cell={'fontSize': '11px', 'padding': '4px 8px', 'textAlign': 'right'},
					style_cell_conditional=[{'if': {'column_id': 'Scenario'}, 'textAlign': 'left'}],
					style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#f8f9fa'}],
				),

				html.P("3. Lifetime", className="fw-semibold small text-muted mb-1"),
				dash_table.DataTable(id='lifetime-table', page_size=20,
					style_table={'overflowX': 'auto', 'marginBottom': '24px'},
					style_header={'backgroundColor': '#343a40', 'color': 'white', 'fontWeight': 'bold', 'fontSize': '11px'},
					style_cell={'fontSize': '11px', 'padding': '4px 8px', 'textAlign': 'right'},
					style_cell_conditional=[{'if': {'column_id': 'Scenario'}, 'textAlign': 'left'}],
					style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#f8f9fa'}],
				),
			]),

			# Charts section
			html.Div(id='charts-section', style={'display': 'none'}, children=[
				dbc.Row([
					dbc.Col(html.H5("Charts", className="fw-bold mt-3 mb-0"), width='auto'),
					dbc.Col(
						dbc.ButtonGroup([
							dbc.Button("3Y",  id='horizon-3',   n_clicks=0, size='sm', outline=True),
							dbc.Button("5Y",  id='horizon-5',   n_clicks=0, size='sm', outline=False),
							dbc.Button("10Y", id='horizon-10',  n_clicks=0, size='sm', outline=True),
							dbc.Button("All", id='horizon-all', n_clicks=0, size='sm', outline=True),
						]),
						width='auto', className='ms-3 mt-3'
					),
				], align='center', className='mb-3'),
				html.Div(id='charts-container'),
			]),

			# Data table
			html.Div(id='data-table-container', className="mt-3"),

		], width=10, className="ps-4"),

	], className="g-0"),

], fluid=True, className="bg-white")

# ============================================================================
# Callbacks
# ============================================================================

@callback(
	Output('date-select', 'options'),
	Input('date-select', 'id'),
	prevent_initial_call=False
)
def load_dates(_):
	dates = get_cutoff_dates()
	return [{'label': d, 'value': d} for d in dates]

@callback(
	Output('model-select', 'options'),
	Input('date-select', 'value'),
	prevent_initial_call=True
)
def load_models(date_select):
	if not date_select:
		return []
	models = get_model_names(date_select)
	return [{'label': m, 'value': m} for m in models]

@callback(
	Output('hierarchy-store', 'data'),
	Input('date-select', 'value'),
	prevent_initial_call=True
)
def load_hierarchy(date_select):
	if not date_select:
		return None
	df = get_hierarchy(date_select)
	return df.to_json(orient='split')

@callback(
	Output('portfolio-select', 'options'),
	Output('portfolio-select', 'value'),
	Input('model-select', 'value'),
	State('hierarchy-store', 'data'),
	prevent_initial_call=True
)
def load_portfolios(model_name, hierarchy_data):
	if not model_name or not hierarchy_data:
		return [], []
	df = pd.read_json(io.StringIO(hierarchy_data), orient='split')
	df = df[df['MODEL_NAME'] == model_name]
	portfolios = sorted(df['PORTFOLIO'].dropna().unique().tolist())
	options = [{'label': p, 'value': p} for p in portfolios]
	return options, portfolios

@callback(
	Output('portfolio-select', 'value', allow_duplicate=True),
	Input('portfolio-all',  'n_clicks'),
	Input('portfolio-none', 'n_clicks'),
	State('portfolio-select', 'options'),
	prevent_initial_call=True
)
def portfolio_all_none(n_all, n_none, options):
	from dash import ctx
	if ctx.triggered_id == 'portfolio-none':
		return []
	return [o['value'] for o in (options or [])]

@callback(
	Output('batch-select', 'options'),
	Output('batch-select', 'value'),
	Input('portfolio-select', 'value'),
	State('hierarchy-store', 'data'),
	prevent_initial_call=True
)
def load_batches(selected_portfolios, hierarchy_data):
	if not hierarchy_data or not selected_portfolios:
		return [], []
	df = pd.read_json(io.StringIO(hierarchy_data), orient='split')
	df = df[df['PORTFOLIO'].isin(selected_portfolios)]
	batches = sorted(df['BATCHNAME'].dropna().unique().tolist())
	options = [{'label': b, 'value': b} for b in batches]
	return options, batches

@callback(
	Output('batch-select', 'value', allow_duplicate=True),
	Input('batch-all',  'n_clicks'),
	Input('batch-none', 'n_clicks'),
	State('batch-select', 'options'),
	prevent_initial_call=True
)
def batch_all_none(n_all, n_none, options):
	from dash import ctx
	if ctx.triggered_id == 'batch-none':
		return []
	return [o['value'] for o in (options or [])]

@callback(
	Output('generate-button', 'disabled'),
	[Input('batch-select', 'value')],
	prevent_initial_call=False
)
def update_button_state(batches):
	return not batches or len(batches) == 0

@callback(
	Output('scenario-select', 'options'),
	Output('scenario-select', 'value'),
	Input('table-store', 'data'),
	State('scenario-select', 'value'),
	prevent_initial_call=True
)
def load_scenarios(stored_data, current_value):
	if not stored_data:
		return [], []
	wide = pd.read_json(io.StringIO(stored_data), orient='split')
	scenarios = sorted(wide['SCENARIO_NAME'].dropna().unique().tolist())
	options = [{'label': s, 'value': s} for s in scenarios]
	# First load: select first 6. Subsequent loads: preserve existing selection.
	new_value = [v for v in current_value if v in scenarios] if current_value else scenarios[:MAX_SCENARIOS]
	return options, new_value

def _is_up(name):
	n = name.lower()
	return bool(re.search(r'_up_|_up$', n))

def _is_down(name):
	n = name.lower()
	return bool(re.search(r'_down_|_down$', n))

@callback(
	Output('scenario-select', 'value', allow_duplicate=True),
	Input('scenario-all',   'n_clicks'),
	Input('scenario-none',  'n_clicks'),
	Input('scenario-up',    'n_clicks'),
	Input('scenario-down',  'n_clicks'),
	Input('scenario-other', 'n_clicks'),
	State('scenario-select', 'options'),
	prevent_initial_call=True
)
def filter_scenarios(n_all, n_none, n_up, n_down, n_other, options):
	from dash import ctx
	all_vals = [o['value'] for o in (options or [])]
	triggered = ctx.triggered_id
	if triggered == 'scenario-none':
		return []
	if triggered == 'scenario-up':
		return [v for v in all_vals if _is_up(v)]
	if triggered == 'scenario-down':
		return [v for v in all_vals if _is_down(v)]
	if triggered == 'scenario-other':
		return [v for v in all_vals if not _is_up(v) and not _is_down(v)]
	return all_vals

@callback(
	Output('data-table-container', 'children'),
	Output('fetch-status', 'children'),
	Output('table-store', 'data'),
	Output('download-button', 'style'),
	Input('generate-button', 'n_clicks'),
	State('date-select', 'value'),
	State('model-select', 'value'),
	State('batch-select', 'value'),
	prevent_initial_call=True
)
def fetch_and_display(n_clicks, date_select, model_name, batch_names):
	hidden = {'display': 'none'}
	if not n_clicks or not date_select or not model_name or not batch_names:
		return None, None, None, hidden

	raw = fetch_data(date_select, model_name, batch_names)
	processed = calculate_columns(raw)

	# Pivot to wide format: one row per (SCENARIO_NAME, BATCHID, ASOFDATE)
	id_cols = [c for c in ['SCENARIO_NAME', 'BATCHID', 'ASOFDATE'] if c in processed.columns]
	wide = processed.pivot_table(
		index=id_cols,
		columns='METRIC',
		values='VALUE',
		aggfunc='first'
	).reset_index()
	wide.columns.name = None

	# Order metric columns by METRIC_TITLES definition, keep id cols first
	metric_order = [m for m in METRIC_TITLES if m in wide.columns]
	display_cols = id_cols + metric_order
	wide = wide[[c for c in display_cols if c in wide.columns]]

	# Build column definitions with formatting
	columns = []
	for col in wide.columns:
		if col in ('ASOFDATE',):
			columns.append({'name': col.title(), 'id': col, 'type': 'datetime'})
		elif col in PERCENT_METRICS:
			columns.append({'name': METRIC_TITLES.get(col, col), 'id': col, 'type': 'numeric',
							'format': {'specifier': '.4%'}})
		elif col in METRIC_TITLES:
			columns.append({'name': METRIC_TITLES.get(col, col), 'id': col, 'type': 'numeric',
							'format': {'specifier': '$,.0f'}})
		else:
			columns.append({'name': col.replace('_', ' ').title(), 'id': col})

	table = dash_table.DataTable(
		data=wide.to_dict('records'),
		columns=columns,
		page_size=20,
		sort_action='native',
		filter_action='native',
		style_table={'overflowX': 'auto'},
		style_header={'backgroundColor': '#f8f9fa', 'fontWeight': 'bold', 'fontSize': '12px'},
		style_cell={'fontSize': '12px', 'padding': '6px 10px', 'textAlign': 'right'},
		style_cell_conditional=[
			{'if': {'column_id': c}, 'textAlign': 'left'}
			for c in ['SCENARIO_NAME', 'BATCHID']
		],
		style_data_conditional=[
			{'if': {'row_index': 'odd'}, 'backgroundColor': '#f8f9fa'}
		],
	)

	status = dbc.Alert(
		f"Loaded {len(wide):,} rows across {len(batch_names)} batch(es).",
		color='success', dismissable=True, className='py-2'
	)
	return table, status, wide.to_json(date_format='iso', orient='split'), {'display': 'inline-block'}

@callback(
	Output('download-csv', 'data'),
	Input('download-button', 'n_clicks'),
	State('table-store', 'data'),
	State('date-select', 'value'),
	State('model-select', 'value'),
	prevent_initial_call=True
)
def download_csv(n_clicks, stored_data, date_select, model_name):
	if not n_clicks or not stored_data:
		return None
	wide = pd.read_json(io.StringIO(stored_data), orient='split')
	filename = f"hvp_{model_name}_{date_select}.csv".replace(' ', '_')
	return dcc.send_data_frame(wide.to_csv, filename, index=False)

def build_figure(wide, metric, fmt, color_map):
	"""Build a single line chart for one metric, one line per scenario."""
	if metric not in wide.columns:
		return go.Figure()

	id_cols = [c for c in ['SCENARIO_NAME', 'ASOFDATE'] if c in wide.columns]

	sub = wide[id_cols + [metric]].dropna(subset=[metric]).sort_values('ASOFDATE')

	fig = go.Figure()
	for scenario, grp in sub.groupby('SCENARIO_NAME'):
		fig.add_trace(go.Scatter(
			x=grp['ASOFDATE'],
			y=grp[metric],
			mode='lines',
			name=scenario,
			line=dict(color=color_map.get(scenario)),
			hovertemplate='%{x}<br>%{y}<extra>' + str(scenario) + '</extra>'
		))

	tick_fmt = '.2%' if fmt == 'percent' else '$,.0f'
	fig.update_layout(
		title=dict(text=METRIC_TITLES.get(metric, metric), font=dict(size=12)),
		margin=dict(l=40, r=10, t=40, b=80),
		height=360,
		showlegend=True,
		legend=dict(
			orientation='h', x=0, y=-0.22,
			font=dict(size=8), itemwidth=30,
			tracegroupgap=2
		),
		yaxis=dict(tickformat=tick_fmt, tickfont=dict(size=9)),
		xaxis=dict(tickfont=dict(size=9)),
		hovermode='x',
		plot_bgcolor='white',
		paper_bgcolor='white',
	)
	fig.update_xaxes(showgrid=True, gridcolor='#f0f0f0')
	fig.update_yaxes(showgrid=True, gridcolor='#f0f0f0')
	return fig


@callback(
	Output('horizon-store', 'data'),
	Output('horizon-3',   'outline'),
	Output('horizon-5',   'outline'),
	Output('horizon-10',  'outline'),
	Output('horizon-all', 'outline'),
	Input('horizon-3',   'n_clicks'),
	Input('horizon-5',   'n_clicks'),
	Input('horizon-10',  'n_clicks'),
	Input('horizon-all', 'n_clicks'),
	prevent_initial_call=True
)
def set_horizon(n3, n5, n10, nall):
	from dash import ctx
	triggered = ctx.triggered_id
	# returns: (years, 3Y-outline, 5Y-outline, 10Y-outline, All-outline)
	if triggered == 'horizon-3':
		return 3,  False, True,  True,  True
	if triggered == 'horizon-10':
		return 10, True,  True,  False, True
	if triggered == 'horizon-all':
		return None, True, True,  True,  False
	return 5, True, False, True, True  # default: 5Y active


@callback(
	Output('charts-container', 'children'),
	Output('charts-section', 'style'),
	Output('scenario-warning', 'children'),
	Input('table-store', 'data'),
	Input('horizon-store', 'data'),
	Input('scenario-select', 'value'),
	State('date-select', 'value'),
	prevent_initial_call=True
)
def update_charts(stored_data, horizon_years, selected_scenarios, cutoff_date):

	if not stored_data:
		return None, {'display': 'none'}, None

	wide = pd.read_json(io.StringIO(stored_data), orient='split')
	wide['ASOFDATE'] = pd.to_datetime(wide['ASOFDATE'])

	# Cap at MAX_SCENARIOS, warn if over
	active = (selected_scenarios or [])[:MAX_SCENARIOS]
	warning = None
	if selected_scenarios and len(selected_scenarios) > MAX_SCENARIOS:
		warning = dbc.Alert(
			f"Showing first {MAX_SCENARIOS} of {len(selected_scenarios)} selected scenarios.",
			color='warning', className='py-1 small'
		)

	wide = wide[wide['SCENARIO_NAME'].isin(active)]

	if horizon_years and cutoff_date:
		cutoff = pd.to_datetime(cutoff_date)
		end_date = cutoff + pd.DateOffset(years=horizon_years)
		wide = wide[wide['ASOFDATE'] <= end_date]

	# Aggregate to one row per (SCENARIO_NAME, ASOFDATE) across batches
	dollar_cols  = [m for m, fmt in CHART_CONFIG if fmt == 'dollar'  and m in wide.columns]
	percent_cols = [m for m, fmt in CHART_CONFIG if fmt == 'percent' and m in wide.columns]
	agg_dict = {**{m: 'sum' for m in dollar_cols}, **{m: 'mean' for m in percent_cols}}
	wide = wide.groupby(['SCENARIO_NAME', 'ASOFDATE'], as_index=False).agg(agg_dict)
	wide = wide.sort_values(['SCENARIO_NAME', 'ASOFDATE'])

	# Cumulative metrics (running sum / initial BOM UPB per scenario)
	if 'bom_principalbalance' in wide.columns:
		initial_bom = wide.groupby('SCENARIO_NAME')['bom_principalbalance'].transform('first')
		if 'chargeoffamount' in wide.columns:
			wide['CCDR'] = (wide.groupby('SCENARIO_NAME')['chargeoffamount'].cumsum() / initial_bom).fillna(0)
		if 'postchargeoffcollections' in wide.columns:
			wide['CumRecoveryR'] = (wide.groupby('SCENARIO_NAME')['postchargeoffcollections'].cumsum() / initial_bom).fillna(0)

	# Build color map
	color_map = {s: SCENARIO_COLORS[i] for i, s in enumerate(active)}

	rows = []
	for i in range(0, len(CHART_CONFIG), 3):
		chunk = CHART_CONFIG[i:i+3]
		cols = []
		for metric, fmt in chunk:
			fig = build_figure(wide, metric, fmt, color_map)
			cols.append(dbc.Col(dcc.Graph(figure=fig, config={'displayModeBar': False}), md=4))
		rows.append(dbc.Row(cols, className='mb-2'))

	return rows, {'display': 'block'}, warning


def compute_summary(wide, window_start, window_end):
	"""Aggregate key metrics per scenario for a given date window."""
	mask = (wide['ASOFDATE'] >= window_start) & (wide['ASOFDATE'] <= window_end)
	w = wide[mask]
	if w.empty:
		return pd.DataFrame()

	def safe_sum(df, col):
		return df[col].sum() if col in df.columns else 0

	def safe_mean(df, col):
		return df[col].mean() if col in df.columns else None

	rows = []
	for scenario, grp in w.groupby('SCENARIO_NAME'):
		last_bom = grp.loc[grp['ASOFDATE'].idxmax(), 'bom_principalbalance'] if 'bom_principalbalance' in grp.columns else None
		rows.append({
			'Scenario':            scenario,
			# Row 1 — balances & cash
			'Last BOM UPB':        last_bom,
			'Total Principal Bal': safe_sum(grp, 'totalprincipalbalance'),
			'Gross Cash':          safe_sum(grp, 'grosscash'),
			# Row 2 — payment rates
			'Sched Pmt Rate':      safe_mean(grp, 'ScheduledPaymentAmountR'),
			'Principal Pmt Rate':  safe_mean(grp, 'PPMT Rate'),
			'Interest Pmt Rate':   safe_mean(grp, 'IPMT Rate'),
			# Row 3 — default & full prepay rates
			'CDR':                 safe_mean(grp, 'CDR'),
			'vSMM':                safe_mean(grp, 'MPR'),
			'MCR':                 safe_mean(grp, 'MCR'),
			# Row 4 — monthly default & total prepay rates
			'MDR':                 safe_mean(grp, 'MDR'),
			'CPR':                 safe_mean(grp, 'CPR'),
			'MPR':                 safe_mean(grp, 'MTPR'),
			# Row 5 — payment amounts
			'Sched Payment':       safe_sum(grp, 'scheduledpaymentamount'),
			'Principal':           safe_sum(grp, 'contractualprincipalpayment'),
			'Interest':            safe_sum(grp, 'interestpayment'),
			# Row 6 — prepayment amounts
			'Total Prepay':        safe_sum(grp, 'principaltotalprepayment'),
			'Full Prepay':         safe_sum(grp, 'principalfullprepayment'),
			'Partial Prepay':      safe_sum(grp, 'principalpartialprepayment'),
			# Row 7 — defaults
			'Charge Off':          safe_sum(grp, 'chargeoffamount'),
			# Row 8 — recovery
			'Recovery':            safe_sum(grp, 'postchargeoffcollections'),
			'Recovery Rate':       safe_mean(grp, 'PostChargeOffCollectionR'),
		})
	return pd.DataFrame(rows)


def compute_lifetime(wide, cutoff):
	"""Compute lifetime weighted metrics per scenario."""
	rows = []
	for scenario, grp in wide.groupby('SCENARIO_NAME'):
		grp = grp.sort_values('ASOFDATE')
		principal = grp['contractualprincipalpayment'].fillna(0) if 'contractualprincipalpayment' in grp.columns else pd.Series(0, index=grp.index)
		months = ((grp['ASOFDATE'] - cutoff) / pd.Timedelta(days=30.44)).clip(lower=0)
		total_principal = principal.sum()
		wal = (months * principal).sum() / total_principal if total_principal > 0 else None

		bom = grp['bom_principalbalance'].fillna(0) if 'bom_principalbalance' in grp.columns else pd.Series(1, index=grp.index)
		wa_cpr = (grp['CPR'] * bom).sum() / bom.sum() if 'CPR' in grp.columns and bom.sum() > 0 else None
		wa_cdr = (grp['CDR'] * bom).sum() / bom.sum() if 'CDR' in grp.columns and bom.sum() > 0 else None

		rows.append({
			'Scenario':   scenario,
			'WAL (Mo)':   wal,
			'WA CPR':     wa_cpr,
			'WA CDR':     wa_cdr,
			'Gross Cash': grp['grosscash'].sum() if 'grosscash' in grp.columns else None,
			'Gross Loss': grp['chargeoffamount'].sum() if 'chargeoffamount' in grp.columns else None,
		})
	return pd.DataFrame(rows)


def make_summary_columns(df):
	"""Build DataTable column definitions with appropriate number formats."""
	dollar_cols = {
		'Last BOM UPB', 'Total Principal Bal', 'Gross Cash',
		'Sched Payment', 'Principal', 'Interest',
		'Total Prepay', 'Full Prepay', 'Partial Prepay', 'Charge Off',
		'Recovery', 'Gross Loss',
	}
	percent_cols = {
		'Sched Pmt Rate', 'Principal Pmt Rate', 'Interest Pmt Rate',
		'CDR', 'vSMM', 'MCR', 'MDR', 'CPR', 'MPR',
		'Recovery Rate', 'WA CPR', 'WA CDR',
	}
	cols = []
	for c in df.columns:
		if c in dollar_cols:
			cols.append({'name': c, 'id': c, 'type': 'numeric', 'format': {'specifier': '$,.0f'}})
		elif c in percent_cols:
			cols.append({'name': c, 'id': c, 'type': 'numeric', 'format': {'specifier': '.2%'}})
		elif c == 'WAL (Mo)':
			cols.append({'name': c, 'id': c, 'type': 'numeric', 'format': {'specifier': '.1f'}})
		else:
			cols.append({'name': c, 'id': c})
	return cols


@callback(
	Output('dtd-table',       'data'),
	Output('dtd-table',       'columns'),
	Output('projected-table', 'data'),
	Output('projected-table', 'columns'),
	Output('lifetime-table',  'data'),
	Output('lifetime-table',  'columns'),
	Output('summary-section', 'style'),
	Input('table-store', 'data'),
	Input('scenario-select', 'value'),
	State('date-select', 'value'),
	prevent_initial_call=True
)
def update_summary(stored_data, selected_scenarios, cutoff_date):
	hidden = {'display': 'none'}
	if not stored_data or not cutoff_date:
		return [], [], [], [], [], [], hidden

	wide = pd.read_json(io.StringIO(stored_data), orient='split')
	wide['ASOFDATE'] = pd.to_datetime(wide['ASOFDATE'])

	# Aggregate to scenario level (same as charts)
	dollar_cols  = [m for m, fmt in CHART_CONFIG if fmt == 'dollar'  and m in wide.columns]
	percent_cols = [m for m, fmt in CHART_CONFIG if fmt == 'percent' and m in wide.columns]
	agg_dict = {**{m: 'sum' for m in dollar_cols}, **{m: 'mean' for m in percent_cols}}
	wide = wide.groupby(['SCENARIO_NAME', 'ASOFDATE'], as_index=False).agg(agg_dict)

	if selected_scenarios:
		wide = wide[wide['SCENARIO_NAME'].isin(selected_scenarios)]

	cutoff = pd.to_datetime(cutoff_date)

	dtd_df  = compute_summary(wide, cutoff - pd.DateOffset(months=12), cutoff)
	proj_df = compute_summary(wide, cutoff + pd.DateOffset(days=1),    cutoff + pd.DateOffset(months=12))
	life_df = compute_lifetime(wide, cutoff)

	return (
		dtd_df.to_dict('records'),  make_summary_columns(dtd_df),
		proj_df.to_dict('records'), make_summary_columns(proj_df),
		life_df.to_dict('records'), make_summary_columns(life_df),
		{'display': 'block'}
	)


if __name__ == '__main__':
	# Local dev: use debug mode on localhost.
	# In Snowpark Container Services, gunicorn calls app.server directly,
	# so this block is not executed inside the container.
	app.run_server(debug=True, host='127.0.0.1', port=8050)
