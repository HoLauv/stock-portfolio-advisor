"""人工构造数据的回归测试；不代表真实行情或历史收益回测。"""
import copy
import json
import unittest
import tempfile
import io
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
import value_model as m
import build_report
import portfolio_ledger

DATE = '2026-09-05'


def meta(**extra):
    return dict(source='synthetic fixture / not real market data',as_of=DATE,
                published_at='2026-08-25',period_end='2026-06-30',**extra)


def stock(code='demo',profile='default'):
    indicators = dict(roe_ttm=18,gross_margin=40,net_margin=20,debt_ratio=35,
                      net_profit_ttm=100,operating_cashflow_ttm=150,prior_net_profit=80,np_cv_3y=.1,
                      rev_yoy=25,np_yoy=25,qoq_trend='improving',forecast='inline',industry_boom=80,
                      pe_pct=20,pb_pct=20,ps_pct=20,rel_industry_discount=-20,
                      main_inflow_20d_pct=1,inflow_5d='in',institution_change_pct=.2,
                      volume_signal='normal',holders_change='down',ma_alignment='bull',rs_60d=10,
                      macd='golden',drawdown_from_250d_high=10,annual_vol=25,
                      rating_buy_ratio=80,news_sentiment='neutral',major_announcement='neutral',research_visits_3m=4,
                      tech_resistance=100,ma60=12,low_3m=10,cycle_recovery='improving',loss_recovery='improving',
                      roe_normalized=12,risk_coverage_ratio=250,net_capital_to_netasset=70,
                      provision_coverage=250,npl_ratio=1,cet1_buffer_pct=4,
                      core_solvency_ratio=200,comprehensive_solvency_ratio=250,normalized_profit_growth_pct=20)
    metadata = {k:meta() for k in indicators}
    metadata['np_cv_3y'].update(positive_mean=True,annual_samples=3)
    for k in ('pe_pct','pb_pct','ps_pct'):
        metadata[k].update(basis='point_in_time',history_months=60)
    metadata['rel_industry_discount']['multiple'] = 'PB' if profile in m.FINANCIAL|{'cyclical'} else 'PE'
    valuation = dict(method='normalized_pe',source='synthetic',sources=['synthetic financial statements'],as_of=DATE,
                     horizon='current_fair_value',assumptions={'normalization':'合成样本，非真实预测','cycle_normalization':'合成完整周期'},
                     scenarios={k:dict(eps_normalized=eps,fair_pe=10) for k,eps in [('bear',1.5),('base',2),('bull',2.5)]})
    if profile in {'bank','broker'}:
        valuation['method'] = 'justified_pb'
        valuation['scenarios'] = {k:dict(bps=10,sustainable_roe_pct=roe,cost_of_equity_pct=10,terminal_growth_pct=2) for k,roe in [('bear',10),('base',12),('bull',14)]}
    if profile=='insurance':
        valuation['method']='embedded_value'
        valuation['scenarios']={k:dict(embedded_value_per_share=20,fair_ev_multiple=x) for k,x in [('bear',.7),('base',1),('bull',1.2)]}
    return dict(code=code,name='合成样本 '+code,industry='合成行业',profile=profile,holding=True,price=15,
                price_meta=meta(),indicators=indicators,indicator_meta=metadata,current_weight=5,
                exposure_group='合成产业链',tradability='normal',tradability_meta=meta(),
                risk=dict(status='checked',events=[],source='synthetic risk check',as_of=DATE),valuation=valuation)


def data(stocks=None):
    market = dict(hs300_ma250_dev=0,volume_ratio_5_250=1,up_ratio_20d=50,broken_net_ratio=10)
    market['indicator_meta']={k:meta() for k in market}
    return dict(synthetic=True,date=DATE,stocks=stocks if stocks is not None else [stock()],market=market,
                portfolio_policy=dict(risk_tolerance='balanced',horizon_years=5,max_drawdown_pct=20,
                                      total_assets=1000000,cash_need_pct=10,equity_budget_pct=70,
                                      other_assets_pct=15,holdings_complete=True,weight_basis='total_assets'))


def first(s):
    return m.evaluate(data([s]))['stocks'][0]


class ModelTests(unittest.TestCase):
    def test_pressure_and_consensus_do_not_change_fair_value(self):
        s=stock()
        a=first(s)
        s['indicators']['tech_resistance']=10000
        s['consensus']=dict(target=1000,institutions=['a','b','c'],source='synthetic',as_of=DATE,horizon='12 months')
        b=first(s)
        self.assertEqual(a['target_price'],20)
        self.assertEqual(a['target_price'],b['target_price'])
        self.assertEqual(a['total'],b['total'])
        self.assertEqual(b['reference_prices']['consensus_target'],1000)

    def test_technical_only_no_value(self):
        s=stock();s.pop('valuation')
        r=first(s)
        self.assertIsNone(r['target_price']);self.assertEqual(r['grade'],'NR')

    def test_empty_data_no_rating_allocation_or_market(self):
        r=m.evaluate(dict(stocks=[dict(code='empty',holding=True)]))
        self.assertIsNone(r['stocks'][0]['total']);self.assertEqual(r['stocks'][0]['grade'],'NR')
        self.assertIsNone(r['market']['temperature']);self.assertIsNone(r['allocation']['cash_pct'])
        self.assertFalse(r['allocation']['targets']);self.assertFalse(r['allocation']['actions'])

    def test_risk_missing_is_not_checked_empty(self):
        s=stock();valid=first(s);s.pop('risk');missing=first(s)
        self.assertNotEqual(valid['grade'],'NR');self.assertEqual(missing['grade'],'NR')
        self.assertFalse(missing['risk_checked'])

    def test_hard_risk_overrides_missing_data(self):
        for event in ('ST','*ST','立案调查','退市预警'):
            r=first(dict(code='risk',risk=dict(events=[event])))
            self.assertEqual(r['grade'],'D');self.assertEqual(r['position_cap'],0)

    def test_unknown_english_risk_not_substring_st(self):
        s=stock();s['risk']['events']=['cost increase']
        self.assertNotEqual(first(s)['grade'],'D')

    def test_financial_profiles_and_debt_not_rewarded(self):
        for profile in m.FINANCIAL:
            s=stock(profile=profile);s['indicators']['debt_ratio']=85;a=first(s)
            s['indicators']['debt_ratio']=99;b=first(s)
            self.assertEqual(a['dims']['Q'],b['dims']['Q'])
            self.assertIsNotNone(a['total'])
            if profile!='bank':
                s['indicators'].pop('provision_coverage');self.assertEqual(first(s)['dims']['Q'],b['dims']['Q'])

    def test_unclassified_financial_not_default_bank(self):
        s=stock();s['profile']='financial';self.assertEqual(first(s)['grade'],'NR')

    def test_cyclical_requires_normalization_and_uses_recovery(self):
        s=stock(profile='cyclical');a=first(s)
        s['indicators']['np_yoy']=-99;self.assertEqual(first(s)['dims']['G'],a['dims']['G'])
        s['valuation']['assumptions'].pop('cycle_normalization');self.assertIsNone(first(s)['target_price'])

    def test_negative_cashflow_ratio_not_sign_proxy(self):
        s=stock();s['indicators'].update(debt_ratio=95,net_profit_ttm=-100,operating_cashflow_ttm=20,ocf_to_np=-.2)
        s['indicator_meta']['rel_industry_discount']['multiple']='PS'
        r=first(s)
        self.assertFalse(any('经营现金流金额为负' in x for x in r['red_flags']))
        self.assertIn('ocf_to_np',r['data_quality']['Q']['not_applicable'])
        s['indicators']['operating_cashflow_ttm']=-20
        r=first(s)
        self.assertTrue(any('经营现金流金额为负' in x for x in r['red_flags']))

    def test_missing_data_cannot_improve_dimension(self):
        s=stock();a=first(s);s['indicators'].pop('gross_margin');b=first(s)
        self.assertLess(b['dims']['Q'],a['dims']['Q'])
        s['indicators'].pop('roe_ttm');self.assertEqual(first(s)['grade'],'NR')

    def test_stale_future_and_missing_sources(self):
        for edit in ({'as_of':'2025-01-01'},{'as_of':'2026-10-01'},{'source':''}):
            s=stock();s['price_meta'].update(edit)
            self.assertEqual(first(s)['grade'],'NR')
        s=stock();s['indicator_meta']['roe_ttm']['published_at']='2026-10-01'
        self.assertEqual(first(s)['grade'],'NR')

    def test_history_cannot_use_today_eps(self):
        s=stock();s['indicator_meta']['pe_pct']['basis']='today_eps'
        self.assertIn('pe_pct',first(s)['data_quality']['V']['missing'])

    def test_peg_units_and_invalid_growth(self):
        self.assertEqual(m.calc_peg(20,20),1)
        for g in (None,0,-10,float('nan')):
            self.assertIsNone(m.calc_peg(20,g))

    def test_valuation_scenarios_invalid_inputs(self):
        for invalid in (0,-1,float('nan'),float('inf'),True):
            s=stock();s['valuation']['scenarios']['base']['fair_pe']=invalid
            self.assertIsNone(first(s)['target_price'])
        s=stock();s['valuation']['scenarios']['bear']['eps_normalized']=100
        self.assertIsNone(first(s)['target_price'])
        s=stock();s['valuation']['horizon']='12_months';self.assertIsNone(first(s)['target_price'])

    def test_pb_formula_and_growth_constraint(self):
        scenario=dict(bps=10,sustainable_roe_pct=12,cost_of_equity_pct=10,terminal_growth_pct=2)
        self.assertAlmostEqual(m.scenario_value('justified_pb',scenario),12.5)
        scenario['terminal_growth_pct']=10
        with self.assertRaises(ValueError):m.scenario_value('justified_pb',scenario)

    def test_dcf_and_ev_bridge(self):
        s=dict(cashflows=[1,1,1],discount_rate_pct=10,terminal_growth_pct=0,terminal_cashflow=1)
        self.assertAlmostEqual(m.scenario_value('fcfe',s),10)
        s.update(net_debt=2,minority_interest=1,non_operating_assets=1,diluted_shares=2)
        self.assertAlmostEqual(m.scenario_value('fcff',s),4)
        self.assertAlmostEqual(m.scenario_value('ev_ebitda',dict(ebitda_normalized=10,fair_multiple=5,net_debt=10,minority_interest=2,non_operating_assets=4,diluted_shares=2)),21)
        s['terminal_growth_pct']=10
        with self.assertRaises(ValueError):m.scenario_value('fcfe',s)

    def test_trading_environment_does_not_change_value(self):
        s=stock();a=first(s)
        s['indicators'].update(ma_alignment='bear',news_sentiment='negative',main_inflow_20d_pct=-10)
        b=first(s);self.assertEqual(a['total'],b['total']);self.assertLess(b['trading_score'],a['trading_score'])

    def test_allocation_constraints_and_zero_grade_exits(self):
        stocks=[stock(str(i)) for i in range(12)]
        for i,s in enumerate(stocks):
            s['industry']=f'industry{i//3}';s['exposure_group']=f'chain{i//4}'
        stocks[0]['risk']['events']=['ST']
        r=m.evaluate(data(stocks));a=r['allocation']
        self.assertEqual(a['status'],'reference');self.assertEqual(a['targets']['0'],0)
        self.assertAlmostEqual(sum(a['targets'].values())+a['cash_pct']+a['other_assets_pct'],100)
        self.assertGreaterEqual(a['cash_pct'],10)
        for s in r['stocks']:
            self.assertLessEqual(a['targets'][s['code']],s['position_cap'])
        for group in ('industry','exposure_group'):
            for name in {s[group] for s in stocks}:
                self.assertLessEqual(sum(a['targets'][s['code']] for s in stocks if s[group]==name),30+1e-6)
        self.assertLessEqual(sum(sorted(a['targets'].values(),reverse=True)[:3]),55)

    def test_policy_trading_or_risk_missing_blocks_allocation(self):
        d=data();d.pop('portfolio_policy');self.assertEqual(m.evaluate(d)['allocation']['status'],'blocked')
        for field in ('risk','tradability_meta'):
            d=data();d['stocks'][0].pop(field);self.assertEqual(m.evaluate(d)['allocation']['status'],'blocked')

    def test_empty_eligible_pool_is_cash_not_phantom_equity(self):
        d=data();d['stocks'][0]['risk']['events']=['ST']
        a=m.evaluate(d)['allocation'];self.assertEqual(a['equity_pct'],0);self.assertEqual(a['cash_pct'],85)

    def test_duplicate_stock_rejected(self):
        with self.assertRaises(ValueError):m.evaluate(data([stock(),stock()]))

    def test_malformed_structures_rejected(self):
        for bad in ([],dict(stocks={}),dict(stocks=[None]),dict(stocks=[dict(code='x',indicator_meta=None)])):
            with self.assertRaises(ValueError):m.evaluate(bad)

    def test_ledger_requires_total_assets_and_handles_margin(self):
        with tempfile.TemporaryDirectory() as folder:
            positions=[dict(code='demo',shares=100,current_price=10,cost_price=8)]
            path=Path(folder)/'positions.json'
            path.write_text(json.dumps(dict(positions=positions)),encoding='utf-8')
            def weights(total_assets):
                output=io.StringIO()
                with redirect_stdout(output):
                    portfolio_ledger.cmd_weights(Namespace(dir=folder,prices=None,total_assets=total_assets))
                return json.loads(output.getvalue())
            self.assertIsNone(weights(None)['positions'][0]['current_weight'])
            self.assertEqual(weights(10000)['positions'][0]['current_weight'],10)
            with self.assertRaises(ValueError):weights(500)
            positions[0]['margin']=True
            path.write_text(json.dumps(dict(positions=positions)),encoding='utf-8')
            self.assertIsNone(weights(10000)['positions'][0]['current_weight'])

    def test_delta_legacy_and_unrated(self):
        r=m.evaluate(data());old=copy.deepcopy(r);old['model_version']='1.0.0'
        self.assertFalse(m.compute_delta(r,old)['deltas'][0]['comparable'])
        r=m.evaluate(data());self.assertEqual(m.compute_delta(r,copy.deepcopy(r))['deltas'][0]['total_delta'],0)
        old=copy.deepcopy(r);old['stocks'][0]['total']=None
        self.assertFalse(m.compute_delta(r,old)['deltas'][0]['comparable'])

    def test_reports_for_complete_empty_and_legacy_delta(self):
        css=Path(__file__).resolve().parent.parent.joinpath('assets/report.css').read_text(encoding='utf-8')
        for r in (m.evaluate(data()),m.evaluate(dict(stocks=[dict(code='empty')]))):
            html=build_report.render(r,css)
            self.assertIn('基准公允价值',html);self.assertNotIn('>None<',html)
        d=data();d['stocks'][0]['name']='<script>alert(1)</script>'
        r=m.evaluate(d);old=copy.deepcopy(r);old['model_version']='1.0'
        html=build_report.render(m.compute_delta(r,old),css)
        self.assertNotIn('<script>alert(1)</script>',html)
        self.assertIn('&lt;script&gt;',html)


if __name__=='__main__':
    unittest.main()
