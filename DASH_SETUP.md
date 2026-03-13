# HVP Dash Dashboard

a professional, hardened dash application for portfolio cashflow engine analysis. this is an enhanced replacement for the streamlit hvp application with improved ui/ux, better security, and more robust error handling.

## features

- **professional ui**: clean, modern dashboard using bootstrap themes
- **improved layout**: organized sections with tabs for different metric categories
- **better performance**: optimized callbacks and data handling
- **hardened security**: input validation, proper error handling, logging
- **responsive design**: works on desktop and tablet displays
- **data export**: download results as excel files (coming soon)

## installation

### 1. create a python environment

using anaconda:
```bash
conda create -n hvp-dash python=3.11
conda activate hvp-dash
```

or using venv:
```bash
python -m venv hvp-dash-env
source hvp-dash-env/bin/activate  # on windows: hvp-dash-env\Scripts\activate
```

### 2. install dependencies

```bash
pip install -r requirements_dash.txt
```

### 3. snowflake authentication

the app uses external browser authentication. ensure your snowflake account and credentials are configured:

- account: `YV35611.east-us-2.azure`
- user: `SAMUEL.BOWIE@CREDIGY.COM` (modify in code if different)
- warehouse: `FRA`

## running the dashboard

```bash
python pcfe_hvp_dash.py
```

the dashboard will be available at: `http://127.0.0.1:8050`

## application structure

### primary files

- **pcfe_hvp_dash.py**: main dash application with layout and core callbacks
- **pcfe_hvp_dash_charts.py**: charting functions and data visualization utilities
- **requirements_dash.txt**: python dependencies

### key configuration

edit these constants in `pcfe_hvp_dash.py` as needed:

```python
USER = 'SAMUEL.BOWIE@CREDIGY.COM'  # your snowflake user
CONNECTION_PARAMS = {...}  # snowflake connection details
DEFAULT_SCENARIOS = ['Actuals', 'Original Pricing', 'Current Refresh', 'Current RUW']
```

## usage workflow

### 1. select data source
- choose between "manual selection" or "most recent run"
- manual selection allows full customization of parameters

### 2. configure parameters
- select cutoff date, model name, and batches
- batch selection is multi-select (select multiple batches)

### 3. generate data
- click "generate actuals and previous projections" button
- this calls snowflake stored procedures and prepares data
- processing may take a few moments

### 4. analyze results
- view 12-month trailing and forward averages
- toggle between totals ($) and percent (%) views
- adjust date range and scenarios to focus analysis
- charts are organized by category (balance, payment, prepayment, default, other)

### 5. export results
- download processed data as excel files (implementation pending)

## development notes

### callback structure

the app uses dash callbacks for reactive updates:

- **parameter cascade**: date → model names → batches
- **data generation**: fetch from snowflake and process
- **display updates**: triggered by scenario/date selection changes

### error handling

all database queries and data processing include try-except blocks with logging:

```python
try:
    # operation
except Exception as e:
    logger.error(f"Error message: {str(e)}")
    # return default or empty result
```

### performance considerations

- data is cached in dcc.Store components to avoid re-fetching
- large date ranges may impact chart rendering - consider filtering
- snowflake stored procedures (usp_datatape_*) can take 20+ seconds for large batches

## improvements over streamlit version

| aspect | streamlit | dash |
|--------|-----------|------|
| ui framework | streamlit built-in | bootstrap 5 |
| error handling | limited | comprehensive with logging |
| input validation | minimal | built-in dropdown validation |
| performance | reruns on any change | targeted callbacks |
| styling | limited customization | full css control |
| deployment | streamlit cloud/server | standard python wsgi servers |
| responsive design | basic | mobile-friendly |

## troubleshooting

### snowflake connection fails
- verify vpn/network connection
- check snowflake credentials and account settings
- ensure `externalbrowser` authenticator is configured

### charts not rendering
- check browser console for errors (f12)
- verify data is populated via "generate data" button
- ensure at least one scenario is selected

### slow performance
- reduce date range
- filter to fewer scenarios
- check snowflake warehouse load

### data mismatch with streamlit
- verify user is the same
- check cutoff date and model selection
- confirm batch selections match

## future enhancements

- [ ] excel export functionality
- [ ] user authentication and role-based access
- [ ] background task processing for long-running operations
- [ ] advanced filtering and drill-down capabilities
- [ ] data refresh scheduling
- [ ] custom metric definitions
- [ ] comparison tools between scenarios

## support

questions, comments, or concerns: ask jacob grigsby
