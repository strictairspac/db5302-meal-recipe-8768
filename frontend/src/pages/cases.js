import {heading, panel} from '../components/common/heading.js';
import {entries, records} from '../components/common/records.js';
import {date, esc} from '../utils/dom.js';
import {topic} from '../constants/project.js';

export function casesPage(state, identity) {
  const {spec, session, cases, runs, orders, warehouse} = state;
  const selected = cases.find(row=>row.id===identity) || cases[0];
  const operator = session.role==='operator';
  const orderOf = id=>orders.find(row=>row.case_id===id);
  const stateOf = row=>row.voided_at ? '已作废' : orderOf(row.id) ? '已出单' : '备料中';
  const rows = cases.map(row=>[`<a href="#cases/${row.id}" ${row.id===selected?.id?'aria-current="true"':''}>${esc(row.title)}</a>`, stateOf(row), esc(row.author), esc(date(row.created_at))]);
  const instruction = selected ? `<h2>${esc(selected.title)}</h2><p>${esc(spec.guidance)}</p>` : '';
  const input = selected ? Object.entries(selected.payload).map(([key, value])=>{
    const label = spec.field_labels[key] || key;
    const rows = Array.isArray(value) && value.every(x=>x && typeof x === 'object' && !Array.isArray(x));
    return panel(label, rows ? entries(value.slice(0,10), spec.field_labels) + (value.length>10?`<p class="note">显示前 10 条，共 ${value.length} 条。</p>`:'') : `<pre>${esc(value)}</pre>`);
  }).join('') : '';
  const order = selected ? orderOf(selected.id) : null;
  const aside = selected ? [
    `<p class="note">该档案记录 ${runs.filter(row=>row.case_id===selected.id).length} 次执行。</p>`,
    selected.voided_at ? `<p class="note">本批已于 ${esc(date(selected.voided_at))} 作废，占用已释放，其他批次可立即占用。</p>` : '',
    order ? `<p class="note">采购单 #${order.id} 已出单；作废不回写，原单照原样回读。</p>` : '',
    operator && !selected.voided_at ? `<p><button class="secondary" id="void-case" data-id="${selected.id}">作废本批并释放占用</button></p>` : '',
    operator ? `<a href="#editor/${selected.id}">复制为新档案</a>` : '',
  ].join('') : `<h2>${esc(spec.customer)}</h2>`;
  const orderPanel = order ? panel(`采购单 #${order.id} · ${esc(date(order.created_at))} 出单`, entries(order.payload)) : '';
  const warehousePanel = panel('仓库现存与占用（实时）', records(
    ['原料', '仓库现存', '占用中', '可占用', '占用批次'],
    warehouse.map(row=>[esc(row.ingredient), esc(row.on_hand), esc(row.occupied), esc(row.available),
      esc(row.holders.map(item=>`批次 ${item.case_id} × ${item.quantity}`).join('；') || '—')]),
    '尚无库存填报。'));
  return `${heading(topic.modules[0], spec.summary, operator?'<a class="button" href="#editor">建立档案</a>':'')}
    <div class="spread"><section aria-label="档案目录">${records([spec.entity_labels[0], '状态', '经办', '建立时间'], rows, '尚未建立档案。经办员可以从演示资料建立第一份。')}</section>
    <aside class="brief">${instruction}${aside}</aside></div>
    ${orderPanel}${warehousePanel}
    ${input ? `<div class="inspection">${input}</div>`:''}`;
}

export function bindCases(api, refresh, fail) {
  const button = document.getElementById('void-case');
  if (!button) return;
  button.addEventListener('click', async()=>{
    button.disabled = true;
    try {
      await api(`/cases/${button.dataset.id}/void`, {method:'POST'});
      await refresh();
    } catch (error) {
      button.disabled = false;
      fail(error);
    }
  });
}
