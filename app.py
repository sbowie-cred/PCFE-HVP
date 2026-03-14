"""
HVP Dashboard - Production Ready Implementation
Enhanced Dash application for portfolio cashflow engine analysis
"""

import dash
from dash import dcc, html, Input, Output, callback
import dash_bootstrap_components as dbc
import pandas as pd
from snowflake_session import session

# ============================================================================
# Configuration
# ============================================================================

METRIC_TITLES = {
	'bom_principalbalance': 'BOM Principal Balance',
	'totalprincipalbalance': 'Total Principal Balance',
	'scheduledpaymentamount': 'Scheduled Payment Amount',
	'contractualprincipalpayment': 'Contractual Principal Payment',
	'PPMT Rate': 'PPMT Rate',
	'interestpayment': 'Interest Payment',
	'IPMT Rate': 'IPMT Rate',
	'principalfullprepayment': 'Principal Full Prepayment',
	'principalpartialprepayment': 'Principal Partial Prepayment',
	'MPR': 'MPR',
	'MCR': 'MCR',
	'principaltotalprepayment': 'Principal Total Prepayment',
	'CPR': 'CPR',
	'chargeoffamount': 'Charge Off Amount',
	'MDR': 'MDR',
	'CDR': 'CDR',
	'postchargeoffcollections': 'Post Charge Off Collections',
	'grosscash': 'Gross Cash',
	'ScheduledPaymentAmountR': 'Scheduled Payment Amount Rate',
	'MTPR': 'MTPR',
	'PostChargeOffCollectionR': 'Post Charge Off Collection Rate',
	'GrossCashR': 'Gross Cash Rate'
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

PERCENT_METRICS = [
	'bom_principalbalance', 'totalprincipalbalance', 'ScheduledPaymentAmountR',
	'PPMT Rate', 'IPMT Rate', 'MPR', 'CPR', 'MCR', 'MTPR', 'MDR', 'CDR',
	'PostChargeOffCollectionR', 'GrossCashR'
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

def get_batches(date_select, model_name):
	"""Retrieve batch names"""

	batches_df = session.sql(f'''
		SELECT DISTINCT b.batchname
		FROM cashflow_engine.fra_pcfe.output_scenario_cashflow cf
		LEFT JOIN datamart.it.batch b ON b.batchid = cf.batchid
		LEFT JOIN cashflow_engine.fra_pcfe.model_scenario s ON cf.scenario_key = s.scenario_key
		LEFT JOIN cashflow_engine.fra_pcfe.model m ON s.model_key = m.model_key
		WHERE s.cutoff_dt = '{date_select}' AND m.model_name = '{model_name}'
		ORDER BY b.batchname
	''').to_pandas()
	return sorted(batches_df['BATCHNAME'].tolist()) if not batches_df.empty else []

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

	bom = df['bom_principalbalance']
	df['PPMT Rate'] = (df['contractualprincipalpayment'] / bom).fillna(0)
	df['IPMT Rate'] = (df['interestpayment'] / bom).fillna(0)
	df['MPR'] = (df['principalfullprepayment'] / bom).fillna(0)
	df['MCR'] = (df['principalpartialprepayment'] / bom).fillna(0)
	df['CPR'] = (1 - (1 - (df['principaltotalprepayment'] / bom)).fillna(0)) ** 12
	df['CDR'] = (1 - (1 - (df['chargeoffamount'] / bom)).fillna(0)) ** 12
	df['MDR'] = (df['chargeoffamount'] / bom).fillna(0)
	df['ScheduledPaymentAmountR'] = (df['scheduledpaymentamount'] / bom).fillna(0)
	df['MTPR'] = (df['principaltotalprepayment'] / bom).fillna(0)
	df['PostChargeOffCollectionR'] = (df['postchargeoffcollections'] / bom).fillna(0)
	df['GrossCashR'] = (df['grosscash'] / bom).fillna(0)

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
	external_stylesheets=[dbc.themes.BOOTSTRAP],
	suppress_callback_exceptions=True
)
app.title = "HVP Dashboard"

# ============================================================================
# Layout
# ============================================================================

app.layout = dbc.Container([
	dbc.Row([
		dbc.Col([
			html.H1("HVP Dashboard", className="mb-0 mt-4 text-primary fw-bold"),
			html.P("Portfolio Cashflow Engine Analysis", className="text-muted")
		], width=12)
	], className="border-bottom mb-4 pb-3"),

	# Primary Inputs
	dbc.Row([
		dbc.Col([
			html.H5("Primary Inputs", className="fw-bold mb-3"),
			dbc.Row([
				dbc.Col([
					dbc.Label("Cutoff Date", className="fw-bold small"),
					dcc.Dropdown(id='date-select', placeholder='Select date...', clearable=False, className="form-control")
				], md=4),
				dbc.Col([
					dbc.Label("Model Name", className="fw-bold small"),
					dcc.Dropdown(id='model-select', placeholder='Select model...', clearable=False, className="form-control")
				], md=4),
				dbc.Col([
					dbc.Label("Batches", className="fw-bold small"),
					dcc.Dropdown(id='batch-select', multi=True, placeholder='Select batches...', className="form-control")
				], md=4)
			], className="g-3")
		], md=12)
	], className="bg-light p-4 rounded mb-4"),

	# Generate Button
	dbc.Row([
		dbc.Col([
			dbc.Button(
				"Fetch & Process Data",
				id='generate-button',
				n_clicks=0,
				color='primary',
				size='lg',
				className='w-100',
				disabled=True
			)
		], width=12)
	], className="mb-4"),

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
	Output('batch-select', 'options'),
	[Input('date-select', 'value'), Input('model-select', 'value')],
	prevent_initial_call=True
)
def load_batches(date_select, model_select):
	if not date_select or not model_select:
		return []
	batches = get_batches(date_select, model_select)
	return [{'label': b, 'value': b} for b in batches]

@callback(
	Output('generate-button', 'disabled'),
	[Input('batch-select', 'value')],
	prevent_initial_call=False
)
def update_button_state(batches):
	return not batches or len(batches) == 0

if __name__ == '__main__':
	app.run_server(debug=True, host='127.0.0.1', port=8050)
