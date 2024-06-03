# -*- coding: utf-8 -*-
import pickle
import numpy as np
import pandas as pd
import pathlib
import plotly.express as px
import plotly.subplots as sp
import plotly.io as pio
pio.renderers.default = 'browser'
pd.options.plotting.backend = "plotly"

from emhass.retrieve_hass import RetrieveHass
from emhass.optimization import Optimization
from emhass.forecast import Forecast
from emhass.utils import get_root, get_yaml_parse, get_days_list, get_logger

# the root folder
root = str(get_root(__file__, num_parent=2))
emhass_conf = {}
emhass_conf['config_path'] = pathlib.Path(root) / 'config_emhass.yaml'
emhass_conf['data_path'] = pathlib.Path(root) / 'data/'
emhass_conf['root_path'] = pathlib.Path(root)

# create logger
logger, ch = get_logger(__name__, emhass_conf, save_to_file=False)

if __name__ == '__main__':
    get_data_from_file = True
    params = None
    show_figures = True
    template = 'presentation'
    
    retrieve_hass_conf, optim_conf, plant_conf = get_yaml_parse(emhass_conf, use_secrets=False)
    retrieve_hass_conf, optim_conf, plant_conf = \
        retrieve_hass_conf, optim_conf, plant_conf
    rh = RetrieveHass(retrieve_hass_conf['hass_url'], retrieve_hass_conf['long_lived_token'], 
                            retrieve_hass_conf['freq'], retrieve_hass_conf['time_zone'],
                            params, emhass_conf, logger)
    if get_data_from_file:
        with open(emhass_conf['data_path'] / 'test_df_final.pkl', 'rb') as inp:
            rh.df_final, days_list, var_list = pickle.load(inp)
        retrieve_hass_conf['var_load'] = str(var_list[0])
        retrieve_hass_conf['var_PV'] = str(var_list[1])
        retrieve_hass_conf['var_interp'] = [retrieve_hass_conf['var_PV'], retrieve_hass_conf['var_load']]
        retrieve_hass_conf['var_replace_zero'] = [retrieve_hass_conf['var_PV']]
    else:
        days_list = get_days_list(retrieve_hass_conf['days_to_retrieve'])
        var_list = [retrieve_hass_conf['var_load'], retrieve_hass_conf['var_PV']]
        rh.get_data(days_list, var_list,
                        minimal_response=False, significant_changes_only=False)
    rh.prepare_data(retrieve_hass_conf['var_load'], load_negative = retrieve_hass_conf['load_negative'],
                            set_zero_min = retrieve_hass_conf['set_zero_min'], 
                            var_replace_zero = retrieve_hass_conf['var_replace_zero'], 
                            var_interp = retrieve_hass_conf['var_interp'])
    df_input_data = rh.df_final.copy()
    
    fcst = Forecast(retrieve_hass_conf, optim_conf, plant_conf,
                            params, emhass_conf, logger, get_data_from_file=get_data_from_file)
    df_weather = fcst.get_weather_forecast(method='csv')
    P_PV_forecast = fcst.get_power_from_weather(df_weather)
    P_load_forecast = fcst.get_load_forecast(method=optim_conf['load_forecast_method'])
    df_input_data = pd.concat([P_PV_forecast, P_load_forecast], axis=1)
    df_input_data.columns = ['P_PV_forecast', 'P_load_forecast']
    
    df_input_data = fcst.get_load_cost_forecast(df_input_data)
    df_input_data = fcst.get_prod_price_forecast(df_input_data)
    input_data_dict = {
        'retrieve_hass_conf': retrieve_hass_conf,
    }
    
    # Set special debug cases
    optim_conf.update({'lp_solver': 'PULP_CBC_CMD'}) # set the name of the linear programming solver that will be used. Options are 'PULP_CBC_CMD', 'GLPK_CMD' and 'COIN_CMD'. 
    optim_conf.update({'lp_solver_path': 'empty'})  # set the path to the LP solver, COIN_CMD default is /usr/bin/cbc
    optim_conf.update({'treat_def_as_semi_cont': [True, True]})
    optim_conf.update({'set_def_constant': [False, False]})
    # optim_conf.update({'P_deferrable_nom': [[500.0, 100.0, 100.0, 500.0], 750.0]})
    
    optim_conf.update({'set_use_battery': True})
    optim_conf.update({'set_nocharge_from_grid': False})
    optim_conf.update({'set_battery_dynamic': True})
    optim_conf.update({'set_nodischarge_to_grid': True})
    
    plant_conf.update({'inverter_is_hybrid': False})
    
    df_input_data.loc[df_input_data.index[25:30],'unit_prod_price'] = -0.07
    df_input_data['P_PV_forecast'] = df_input_data['P_PV_forecast']*2
    P_PV_forecast = P_PV_forecast*2
    
    costfun = 'profit'
    opt = Optimization(retrieve_hass_conf, optim_conf, plant_conf, 
                       fcst.var_load_cost, fcst.var_prod_price,  
                       costfun, emhass_conf, logger)
    opt_res_dayahead = opt.perform_dayahead_forecast_optim(
        df_input_data, P_PV_forecast, P_load_forecast)
    
    # Let's plot the input data
    fig_inputs_dah = df_input_data.plot()
    fig_inputs_dah.layout.template = template
    fig_inputs_dah.update_yaxes(title_text = "Powers (W) and Costs(EUR)")
    fig_inputs_dah.update_xaxes(title_text = "Time")
    if show_figures:
        fig_inputs_dah.show()
    
    vars_to_plot = ['P_deferrable0', 'P_deferrable1','P_grid', 'P_PV', 'P_PV_curtailment']
    if plant_conf['inverter_is_hybrid']:
        vars_to_plot = vars_to_plot + ['P_hybrid_inverter']
    if optim_conf['set_use_battery']:
        vars_to_plot = vars_to_plot + ['P_batt'] + ['SOC_opt']
    fig_res_dah = opt_res_dayahead[vars_to_plot].plot() # 'P_def_start_0', 'P_def_start_1', 'P_def_bin2_0', 'P_def_bin2_1'
    fig_res_dah.layout.template = template
    fig_res_dah.update_yaxes(title_text = "Powers (W)")
    fig_res_dah.update_xaxes(title_text = "Time")
    if show_figures:
        fig_res_dah.show()
    
    print("System with: PV, two deferrable loads, dayahead optimization, profit >> total cost function sum: "+\
        str(opt_res_dayahead['cost_profit'].sum())+", Status: "+opt_res_dayahead['optim_status'].unique().item())
    
    print(opt_res_dayahead[vars_to_plot])
    