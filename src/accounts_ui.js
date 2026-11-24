/* Янтарь: кнопки «Аккаунты» внутри Antigravity. */
(function () {
  if (typeof document === 'undefined' || document.getElementById('amber-accounts-ui')) return;
  var st = document.createElement('style');
  st.id = 'amber-accounts-ui';
  st.textContent = [
    '.amber-acc-btn{position:fixed;left:14px;bottom:52px;z-index:99998;display:flex;align-items:center;gap:8px;',
    'max-width:210px;padding:7px 12px;border-radius:999px;border:1px solid rgba(255,255,255,.10);',
    'background:rgba(255,255,255,.055);color:#e8e8e8;font:500 12px/1.2 system-ui,sans-serif;cursor:pointer;',
    'backdrop-filter:blur(8px);transition:background .15s ease,border-color .15s ease}',
    '.amber-acc-btn:hover{background:rgba(255,255,255,.12);border-color:rgba(255,255,255,.22)}',
    '.amber-acc-dot{width:8px;height:8px;border-radius:50%;background:#8ab4f8;box-shadow:0 0 8px #8ab4f8aa;flex:none}',
    '#amber-acc-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.amber-acc-modal{position:fixed;inset:0;z-index:99999;display:none;align-items:center;justify-content:center;',
    'background:rgba(0,0,0,.55);backdrop-filter:blur(4px)}',
    '.amber-acc-modal.show{display:flex}',
    '.amber-acc-card{width:min(420px,92vw);border-radius:18px;padding:18px;background:#1c1c1f;',
    'border:1px solid rgba(255,255,255,.09);box-shadow:0 24px 70px rgba(0,0,0,.6);color:#eee;',
    'font:13px/1.45 system-ui,sans-serif}',
    '.amber-acc-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}',
    '.amber-acc-head b{font-size:15px}',
    '.amber-acc-x{border:0;background:transparent;color:#aaa;font-size:20px;cursor:pointer}',
    '.amber-acc-row{display:flex;justify-content:space-between;align-items:center;gap:10px;',
    'padding:10px 12px;margin:6px 0;border-radius:12px;background:rgba(255,255,255,.045)}',
    '.amber-acc-row.active{background:rgba(138,180,248,.14);border:1px solid rgba(138,180,248,.35)}',
    '.amber-acc-row small{display:block;color:#999;font-size:11px}',
    '.amber-acc-go{border:0;border-radius:9px;padding:6px 11px;background:#8ab4f8;color:#10233d;',
    'font-weight:600;cursor:pointer}',
    '.amber-acc-add{width:100%;margin-top:12px;border:1px dashed rgba(255,255,255,.2);border-radius:12px;',
    'padding:10px;background:transparent;color:#ddd;cursor:pointer}',
    '.amber-acc-add:hover{background:rgba(255,255,255,.06)}',
    '.amber-acc-addrow{display:flex;gap:8px;margin-top:12px}',
    '.amber-acc-input{flex:1;min-width:0;border:1px solid rgba(255,255,255,.16);border-radius:12px;',
    'padding:9px 11px;background:rgba(255,255,255,.05);color:#eee;font:inherit;outline:none}',
    '.amber-acc-input:focus{border-color:#8ab4f8}',
    '.amber-acc-addok{border:0;border-radius:12px;padding:9px 14px;background:#8ab4f8;color:#10233d;',
    'font-weight:600;cursor:pointer}'
  ].join('\n');
  document.head.appendChild(st);

  var btn = document.createElement('button');
  btn.className = 'amber-acc-btn';
  btn.innerHTML = '<span class="amber-acc-dot"></span><span id="amber-acc-label">Аккаунт</span>';
  document.body.appendChild(btn);

  var modal = document.createElement('div');
  modal.className = 'amber-acc-modal';
  modal.innerHTML = '<div class="amber-acc-card">' +
    '<div class="amber-acc-head"><b>Google-аккаунты</b><button class="amber-acc-x">×</button></div>' +
    '<div id="amber-acc-list"></div>' +
    '<div class="amber-acc-addrow"><input class="amber-acc-input" placeholder="Название аккаунта" value="Рабочий"><button class="amber-acc-addok">Добавить</button></div>' +
    '</div>';
  document.body.appendChild(modal);

  function send(cmd, label) {
    window.__amberCommand = { cmd: cmd, label: label || '', ts: Date.now() };
    modal.classList.remove('show');
  }

  function refresh() {
    var d = window.__amberAccountData || {};
    var lab = document.getElementById('amber-acc-label');
    if (lab) {
      var email = (d.current && d.current.email) || '';
      lab.textContent = email ? email.split('@')[0] : 'Войти в аккаунт';
    }
    var list = document.getElementById('amber-acc-list');
    if (!list) return;
    var profiles = Array.isArray(d.profiles) ? d.profiles : [];
    if (!profiles.length) {
      list.innerHTML = '<div class="amber-acc-row">Нет сохранённых аккаунтов</div>';
      return;
    }
    list.innerHTML = '';
    profiles.forEach(function (p) {
      var row = document.createElement('div');
      row.className = 'amber-acc-row' + (p.active ? ' active' : '');
      var info = document.createElement('div');
      info.innerHTML = '<b></b><small></small>';
      info.querySelector('b').textContent = p.label || p.key;
      info.querySelector('small').textContent = p.email + (p.active ? ' · сейчас' : '');
      var go = document.createElement('button');
      go.className = 'amber-acc-go';
      go.textContent = p.active ? 'Активен' : 'Войти';
      go.disabled = !!p.active;
      go.onclick = function () { send('use', p.label || p.key); };
      row.appendChild(info);
      row.appendChild(go);
      list.appendChild(row);
    });
  }

  btn.onclick = function () { refresh(); modal.classList.add('show'); };
  modal.querySelector('.amber-acc-x').onclick = function () { modal.classList.remove('show'); };
  modal.onclick = function (e) { if (e.target === modal) modal.classList.remove('show'); };
  modal.querySelector('.amber-acc-addok').onclick = function () {
    var field = modal.querySelector('.amber-acc-input');
    var name = (field && field.value || '').trim();
    if (name) send('add', name);
  };
  setInterval(refresh, 1000);
  refresh();
})();
