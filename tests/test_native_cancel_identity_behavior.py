"""Run actual Swift target-identity validation on multirow OCR captures."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope='module')
def cancel_identity(tmp_path_factory):
    compiler = shutil.which('swiftc')
    if not compiler:
        pytest.skip('Swift compiler required')
    source = (Path(__file__).resolve().parents[1]/'native/foundersc_ax_executor/Sources/FounderscNativeAX/main.swift').read_text()
    sections = [('private struct Bounds:', 'private struct Capabilities:'),
        ('private struct QueryReadback:', 'private struct CancelReadback:'),
        ('private struct OCRToken:', 'private func captureFounderWindow('),
        ('private struct OrderInput {', 'private func parseOrderInput('),
        ('private func normalizedHeader(', 'private func summaryNumber('),
        ('private func normalizedCode(', 'private func currentOrderReadback('),
        ('private func normalizedBrokerSide(', 'private func actionStripTokens(')]
    routines = '\n'.join(source[source.index(a):source.index(b)] for a,b in sections)
    directory = tmp_path_factory.mktemp('cancel-identity')
    swift, exe = directory/'main.swift', directory/'test'
    swift.write_text('import Foundation\n'+routines+'''
private struct Fixture: Decodable {
    let query: QueryReadback
    let tokens: [OCRToken]
    let shape: TableShape
    let targetIndex: Int
}
let data = FileHandle.standardInput.readDataToEndOfFile()
private let fixture = try JSONDecoder().decode(Fixture.self, from: data)
private let order = OrderInput(code: "512010", side: "buy", priceText: "0.37",
    price: Decimal(string: "0.37")!, quantity: 200, expectedFingerprint: "123******890")
print(cancelRowProofMode(query: fixture.query, tokens: fixture.tokens, shape: fixture.shape,
    targetIndex: fixture.targetIndex, input: CancelInput(order: order, orderId: "7000015")) ?? "UNPROVEN")
''')
    subprocess.run([compiler, str(swift), '-o', str(exe)], capture_output=True, check=True, timeout=45)
    return exe


def capture():
    values = {'证券代码':'512010','委托编号':'7000015','委托价格':'0.3700','委托数量':'200','买卖标志':'买入'}
    columns = [{'title':k,'bounds':{'x':i*100,'y':0,'width':90,'height':400}} for i,k in enumerate(values)]
    tokens = [{'text':v,'confidence':.99,'bounds':{'x':i*100+20,'y':100,'width':30,'height':10}}
              for i,v in enumerate(values.values())]
    tokens.append({'text':'已撤','confidence':.1,'bounds':{'x':550,'y':70,'width':30,'height':10}})
    rows = [{**values,'委托编号':'7000001'},values]
    return {'query':{'kind':'today-orders','captureProven':True,'navigationLabelCount':1,
        'navigationClickMode':'test','headers':list(values),'rows':rows,'summaryValues':{},'rowCount':2,
        'parsingProven':False,'emptyStateProven':False,'criticalConfidenceFloor':.5,
        'criticalConfidenceProven':False,'minimumCriticalConfidenceObserved':.1,
        'lowConfidenceCriticalHeaders':['状态说明'],'ocrLineCount':6,'observedAt':'test'},
        'tokens':tokens,'shape':{'bounds':None,'rowCount':2,'columnCount':5,'cellCount':10,
        'readableValueCount':0,'auditComplete':True,'columns':columns,
        'rowBounds':[{'x':0,'y':70,'width':600,'height':15},{'x':0,'y':100,'width':600,'height':15}],
        'tableAttributeNames':None,'rowAttributeNames':None},'targetIndex':1}


@pytest.mark.parametrize('fault,expected', [
    ('none','exact_order_tuple'), ('side_confidence','exact_numeric_tuple_bounded_side_suffix'),
    ('bounded_side','exact_numeric_tuple_bounded_side_suffix'),
    ('price_confidence','UNPROVEN'), ('missing_id_token','UNPROVEN'),
    ('changed_order','UNPROVEN'), ('changed_quantity','UNPROVEN'), ('changed_side','UNPROVEN'),
    ('duplicate_column','UNPROVEN'), ('row_count','UNPROVEN'), ('wrong_index','UNPROVEN'),
])
def test_cancel_identity_ignores_unrelated_status_but_requires_exact_selected_tuple(cancel_identity,fault,expected):
    value = capture()
    if fault == 'side_confidence': value['tokens'][4]['confidence'] = .1
    elif fault == 'bounded_side': value['query']['rows'][1]['买卖标志']='头入'
    elif fault == 'price_confidence': value['tokens'][2]['confidence']=.1
    elif fault == 'missing_id_token': value['tokens'].pop(1)
    elif fault == 'changed_order': value['query']['rows'][1]['委托编号']='7000016'
    elif fault == 'changed_quantity': value['query']['rows'][1]['委托数量']='100'
    elif fault == 'changed_side': value['query']['rows'][1]['买卖标志']='卖出'
    elif fault == 'duplicate_column': value['shape']['columns'].append(value['shape']['columns'][0])
    elif fault == 'row_count': value['query']['rows'].pop(0)
    elif fault == 'wrong_index': value['targetIndex']=0
    result = subprocess.run([str(cancel_identity)],input=json.dumps(value),capture_output=True,
                            text=True,check=True,timeout=3)
    assert result.stdout.strip() == expected
