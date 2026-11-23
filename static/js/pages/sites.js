import { api, chip, escapeHtml } from '../api.js';

export async function renderSites(el) {
  const [data, counts, protocols, compat] = await Promise.all([
    api('/api/sites'),
    api('/api/site-counts'),
    api('/api/protocols'),
    api('/api/compat_cut/dash'),
  ]);
  const items = data.items || [];
  const activeProto = (protocols.items || []).find((p) => p.status === '生效');
  const landings = compat.landings || [];
  const aligned = compat.aligned === true;
  const chipCls = aligned ? 'ok' : (compat.chip === '兼容已亮' ? 'warn' : 'bad');

  el.innerHTML = `
    <div class="card">
      <h2>
        <span class="chip ${chipCls}">${escapeHtml(compat.chip || '字段版旧')}</span>
        <span class="chip ${aligned ? 'ok' : 'bad'}">字段版号 ${escapeHtml(compat.field_version || '-')}</span>
        试验中心目录
      </h2>
      <p class="muted">登记临床试验中心、启停状态与访视抓取配额。停用前须先结束采集中批次。</p>
      <div class="grid">
        <div class="stat"><div class="n">${counts.total || 0}</div><div class="l">中心总数</div></div>
        <div class="stat"><div class="n">${counts['启用'] || 0}</div><div class="l">启用</div></div>
        <div class="stat"><div class="n">${counts['观察'] || 0}</div><div class="l">观察</div></div>
        <div class="stat"><div class="n">${counts['停用'] || 0}</div><div class="l">停用</div></div>
      </div>
      <div class="row">
        <input id="sname" placeholder="中心名称" />
        <input id="sregion" placeholder="区域" />
        <input id="sprincipal" placeholder="负责人" />
        <input id="squota" type="number" value="50" style="width:100px" title="配额" />
        <input id="snote" placeholder="备注" />
        <button id="create">登记中心</button>
      </div>
      <p class="muted">当前生效方案：${activeProto ? escapeHtml(activeProto.title + ' @ ' + activeProto.version) : '无'}</p>
    </div>
    <div class="card" id="compatCard">
      <h2>换版兼容落点 · 读轨收口</h2>
      <p class="muted">兼容徽标须与字段版号、落点行次三者对齐；错列灌批、质控扫描与补采排队都按落点行口径放行。</p>
      <div class="grid">
        <div class="stat"><div class="n">${escapeHtml(compat.field_version || '-')}</div><div class="l">当刻字段版号</div></div>
        <div class="stat"><div class="n">${escapeHtml(compat.pinned_version || '-')}</div><div class="l">落点钉住版号</div></div>
        <div class="stat"><div class="n">${compat.landing_id || '-'}</div><div class="l">落点行次</div></div>
        <div class="stat"><div class="n">${compat.landing_count || 0}</div><div class="l">landed 落点</div></div>
        <div class="stat"><div class="n">${escapeHtml(compat.read_track || '-')}</div><div class="l">读轨</div></div>
      </div>
      <p class="${aligned ? 'muted' : 'err'}" id="compatReason">
        ${aligned ? '徽标 / 字段版号 / 落点行已对齐，读轨收口到切流账册。' : '未对齐：' + escapeHtml(compat.reason || '')}
      </p>
      <div class="row">
        <button id="compatCommit">落台钉定</button>
        <button id="compatReload" class="ghost">刷新落点</button>
      </div>
      <h3 style="font-size:15px;margin:14px 0 6px">换版兼容落点队列（行次）</h3>
      <table>
        <thead>
          <tr><th>行次</th><th>字段版号</th><th>指纹</th><th>读轨</th><th>拒回刷</th><th>状态</th><th>时间</th></tr>
        </thead>
        <tbody id="compatLandingBody">
          ${landings.length ? landings.map((r) => `
            <tr>
              <td><button data-landing="${r.id}" class="ghost">#${r.id}</button></td>
              <td>${escapeHtml(r.field_version || '-')}</td>
              <td class="muted"><code>${escapeHtml((r.fingerprint || '').slice(0, 16))}…</code></td>
              <td>${escapeHtml(r.read_track || '-')}</td>
              <td>${r.reject_refresh ? '是' : '否'}</td>
              <td>${chip(r.status === 'landed' ? '生效' : '废止')}</td>
              <td class="muted">${escapeHtml(r.created_at || '')}</td>
            </tr>`).join('') : '<tr><td colspan="7" class="muted">暂无落点行（仅亮徽标不算数）</td></tr>'}
        </tbody>
      </table>
      <div id="compatDetail" class="detail-box" style="margin-top:12px">选择落点行次查看指纹对照详情。</div>
    </div>
    <div class="card">
      <div class="row">
        <select id="filterStatus">
          <option value="">全部状态</option>
          <option>启用</option>
          <option>观察</option>
          <option>停用</option>
        </select>
        <button id="refresh" class="ghost">刷新</button>
      </div>
      <table>
        <thead>
          <tr>
            <th>编码</th><th>名称</th><th>状态</th><th>配额</th>
            <th>批次</th><th>缺口合计</th><th>区域/负责人</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${items.map((s) => `
            <tr data-id="${s.id}">
              <td>${escapeHtml(s.site_code)}</td>
              <td>
                <div>${escapeHtml(s.name)}</div>
                <div class="muted">${escapeHtml(s.note || '')}</div>
              </td>
              <td>${chip(s.status)}</td>
              <td>${s.quota}</td>
              <td>${s.batch_count}</td>
              <td>${s.gap_total}</td>
              <td>${escapeHtml(s.region || '-')} / ${escapeHtml(s.principal || '-')}</td>
              <td class="row">
                <button data-st="启用" data-id="${s.id}">启用</button>
                <button data-st="观察" data-id="${s.id}" class="warn">观察</button>
                <button data-st="停用" data-id="${s.id}" class="danger">停用</button>
                <button data-q="${s.id}">配额+10</button>
                <button data-detail="${s.id}" class="ghost">详情</button>
              </td>
            </tr>`).join('')}
        </tbody>
      </table>
      <div id="siteDetail" class="detail-box" style="margin-top:12px">选择一行查看批次明细。</div>
    </div>
    <div class="card">
      <h2>方案版本</h2>
      <p class="muted">生效方案决定抓取时的必填字段与访视编码清单。同时只能有一个生效方案。</p>
      <div class="row">
        <input id="ptitle" placeholder="方案标题" />
        <input id="pver" placeholder="版本" value="1.1" style="width:90px" />
        <input id="pfields" placeholder="必填字段逗号分隔" style="min-width:260px"
          value="subject_key,visit_code,visit_date,investigator,weight_kg" />
        <input id="pvisits" placeholder="访视编码" value="V1,V2,V3,EOT" />
        <button id="pcreate">登记方案</button>
      </div>
      <table>
        <thead><tr><th>编码</th><th>标题</th><th>版本</th><th>状态</th><th>必填字段</th><th>操作</th></tr></thead>
        <tbody>
          ${(protocols.items || []).map((p) => `
            <tr>
              <td>${escapeHtml(p.protocol_code)}</td>
              <td>${escapeHtml(p.title)}</td>
              <td>${escapeHtml(p.version)}</td>
              <td>${chip(p.status)}</td>
              <td class="muted">${escapeHtml((p.required_fields_list || []).join(', '))}</td>
              <td class="row">
                <button data-pstatus="生效" data-pid="${p.id}">生效</button>
                <button data-pstatus="草稿" data-pid="${p.id}" class="ghost">草稿</button>
                <button data-pstatus="废止" data-pid="${p.id}" class="danger">废止</button>
              </td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;

  const errBox = (msg) => {
    const box = el.querySelector('#siteDetail');
    box.textContent = '错误：' + msg;
  };

  el.querySelector('#create').onclick = async () => {
    try {
      await api('/api/sites', {
        method: 'POST',
        body: JSON.stringify({
          name: el.querySelector('#sname').value,
          region: el.querySelector('#sregion').value,
          principal: el.querySelector('#sprincipal').value,
          quota: Number(el.querySelector('#squota').value || 50),
          note: el.querySelector('#snote').value,
        }),
      });
      await renderSites(el);
    } catch (e) { errBox(e.message); }
  };

  el.querySelector('#refresh').onclick = () => renderSites(el);

  const compatDetail = el.querySelector('#compatDetail');
  const compatCommit = el.querySelector('#compatCommit');
  if (compatCommit) compatCommit.onclick = async () => {
    try {
      const r = await api('/api/compat_cut/commit', {
        method: 'POST',
        body: JSON.stringify({ note: '中心列表落台' }),
      });
      if (!r.aligned) throw new Error(r.reason || '落台未对齐');
      await renderSites(el);
    } catch (e) {
      compatDetail.className = 'detail-box err';
      compatDetail.textContent = '落台失败：' + e.message;
    }
  };
  el.querySelector('#compatReload').onclick = () => renderSites(el);
  el.querySelectorAll('[data-landing]').forEach((btn) => {
    btn.onclick = async () => {
      const row = landings.find((r) => String(r.id) === btn.dataset.landing);
      compatDetail.className = 'detail-box';
      compatDetail.textContent = JSON.stringify({
        落点行次: row?.id,
        字段版号: row?.field_version,
        当刻版号: compat.field_version,
        落点指纹: row?.fingerprint,
        当刻指纹: compat.fingerprint,
        读轨: row?.read_track,
        拒回刷: row?.reject_refresh,
        状态: row?.status,
        对齐: row?.status === 'landed' && row?.fingerprint === compat.fingerprint
          && row?.field_version === compat.field_version,
        说明: compat.reason || '已对齐',
      }, null, 2);
    };
  });
  el.querySelector('#filterStatus').onchange = async (ev) => {
    const status = ev.target.value;
    const url = status ? `/api/sites?status=${encodeURIComponent(status)}` : '/api/sites';
    const filtered = await api(url);
    const tbody = el.querySelector('tbody');
    tbody.innerHTML = (filtered.items || []).map((s) => `
      <tr data-id="${s.id}">
        <td>${escapeHtml(s.site_code)}</td>
        <td>${escapeHtml(s.name)}</td>
        <td>${chip(s.status)}</td>
        <td>${s.quota}</td>
        <td>${s.batch_count}</td>
        <td>${s.gap_total}</td>
        <td>${escapeHtml(s.region || '-')} / ${escapeHtml(s.principal || '-')}</td>
        <td class="muted">请点刷新回到完整操作区</td>
      </tr>`).join('');
  };

  el.querySelectorAll('[data-st]').forEach((btn) => {
    btn.onclick = async () => {
      try {
        await api(`/api/sites/${btn.dataset.id}/status`, {
          method: 'POST',
          body: JSON.stringify({ status: btn.dataset.st }),
        });
        await renderSites(el);
      } catch (e) { errBox(e.message); }
    };
  });

  el.querySelectorAll('[data-q]').forEach((btn) => {
    btn.onclick = async () => {
      const site = items.find((x) => String(x.id) === btn.dataset.q);
      try {
        await api(`/api/sites/${btn.dataset.q}/quota`, {
          method: 'POST',
          body: JSON.stringify({ quota: (site?.quota || 50) + 10 }),
        });
        await renderSites(el);
      } catch (e) { errBox(e.message); }
    };
  });

  el.querySelectorAll('[data-detail]').forEach((btn) => {
    btn.onclick = async () => {
      try {
        const detail = await api(`/api/sites/${btn.dataset.detail}`);
        el.querySelector('#siteDetail').textContent = JSON.stringify({
          中心: detail.name,
          状态: detail.status,
          开放缺口: detail.open_gaps,
          批次: (detail.batches || []).map((b) => ({
            编码: b.batch_code,
            状态: b.status,
            行数: b.item_count,
            缺口: b.gap_count,
          })),
        }, null, 2);
      } catch (e) { errBox(e.message); }
    };
  });

  el.querySelector('#pcreate').onclick = async () => {
    const fields = el.querySelector('#pfields').value.split(',').map((x) => x.trim()).filter(Boolean);
    const visits = el.querySelector('#pvisits').value.split(',').map((x) => x.trim()).filter(Boolean);
    try {
      await api('/api/protocols', {
        method: 'POST',
        body: JSON.stringify({
          title: el.querySelector('#ptitle').value,
          version: el.querySelector('#pver').value,
          required_fields: fields,
          visit_codes: visits,
        }),
      });
      await renderSites(el);
    } catch (e) { errBox(e.message); }
  };

  el.querySelectorAll('[data-pstatus]').forEach((btn) => {
    btn.onclick = async () => {
      try {
        await api(`/api/protocols/${btn.dataset.pid}/status`, {
          method: 'POST',
          body: JSON.stringify({ status: btn.dataset.pstatus }),
        });
        await renderSites(el);
      } catch (e) { errBox(e.message); }
    };
  });
}
