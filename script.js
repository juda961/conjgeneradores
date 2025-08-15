document.addEventListener("DOMContentLoaded", () => {
  const ta = document.getElementById("vectores");
  const btn = document.getElementById("btn-comprobar");
  const resumenDiv = document.getElementById("resumen");
  const pasosDiv = document.getElementById("pasos");
  const modoNumber = document.getElementById("modoNumber");
  const precisionInput = document.getElementById("precision");

  function fmtNumber(x) {
    const mode = modoNumber.value;
    const prec = Math.max(1, Math.min(12, parseInt(precisionInput.value || "6", 10)));
    if (!isFinite(x)) return x > 0 ? "∞" : (x < 0 ? "−∞" : "NaN");
    if (mode === "fraction") {
      try { return math.fraction(x).toString(); }
      catch { return Number(x).toFixed(prec); }
    }
    return Number(x).toFixed(prec);
  }

  function parseVectors(text) {
    const lines = text.split("\n").map(s => s.trim()).filter(s => s.length > 0);
    if (lines.length === 0) throw new Error("No ingresaste vectores.");

    const cols = lines.map((line, idx) => {
      const parts = line.includes(",") ? line.split(",") : line.split(/\s+/);
      const nums = parts.map(p => {
        const v = Number(p.trim());
        if (!isFinite(v)) throw new Error(`Componente no numérica en la línea ${idx+1}.`);
        return v;
      });
      return nums;
    });

    const m = cols[0].length;
    cols.forEach((c, i) => {
      if (c.length !== m) {
        throw new Error(`Todos los vectores deben tener ${m} componentes. Línea ${i+1} tiene ${c.length}.`);
      }
    });

    const nvec = cols.length;
    const A = Array.from({length: m}, () => Array(nvec).fill(0));
    for (let j = 0; j < nvec; j++) {
      for (let i = 0; i < m; i++) {
        A[i][j] = cols[j][i];
      }
    }
    return {A, m, nvec, cols};
  }

  const clone = M => M.map(r => r.slice());

  function matrixToTable(M, headerLabel = "") {
    let html = '<table class="tabla">';
    if (headerLabel) {
      html += `<thead><tr><th colspan="${M[0].length}">${headerLabel}</th></tr></thead>`;
    }
    html += "<tbody>";
    for (const row of M) {
      html += "<tr>";
      for (const val of row) html += `<td>${fmtNumber(val)}</td>`;
      html += "</tr>";
    }
    html += "</tbody></table>";
    return html;
  }

  function rrefWithSteps(M) {
    const A = clone(M);
    const rows = A.length;
    const cols = A[0].length;
    let r = 0;
    const snapshots = [];
    const eps = 1e-12;

    function snap(op) { snapshots.push({op, mat: clone(A)}); }

    for (let c = 0; c < cols && r < rows; c++) {
      let piv = r;
      for (let i = r+1; i < rows; i++) {
        if (Math.abs(A[i][c]) > Math.abs(A[piv][c])) piv = i;
      }
      if (Math.abs(A[piv][c]) < eps) continue;

      if (piv !== r) {
        [A[piv], A[r]] = [A[r], A[piv]];
        snap(`Intercambia R${r+1} ↔ R${piv+1}`);
      }
      const pivVal = A[r][c];
      if (Math.abs(pivVal - 1) > eps) {
        for (let j = 0; j < cols; j++) A[r][j] /= pivVal;
        snap(`Normaliza R${r+1}`);
      }
      for (let i = 0; i < rows; i++) {
        if (i === r) continue;
        const factor = A[i][c];
        if (Math.abs(factor) > eps) {
          for (let j = 0; j < cols; j++) {
            A[i][j] -= factor * A[r][j];
            if (Math.abs(A[i][j]) < eps) A[i][j] = 0;
          }
          snap(`R${i+1} := R${i+1} - (${fmtNumber(factor)})·R${r+1}`);
        }
      }
      r++;
    }

    const pivotCols = [];
    for (let c = 0; c < cols; c++) {
      let oneCount = 0, anyOther = false;
      for (let i = 0; i < rows; i++) {
        if (Math.abs(A[i][c] - 1) < 1e-9) oneCount++;
        else if (Math.abs(A[i][c]) > 1e-9) anyOther = true;
      }
      if (oneCount === 1 && !anyOther) pivotCols.push(c);
    }
    return {R: A, rank: pivotCols.length, pivotCols, snapshots};
  }

  btn.addEventListener("click", () => {
    resumenDiv.style.display = "none";
    pasosDiv.style.display = "none";
    resumenDiv.innerHTML = "";
    pasosDiv.innerHTML = "";

    try {
      const {A, m, nvec} = parseVectors(ta.value.trim());
      let pasosHTML = `<h3>Matriz con vectores como columnas (R<sup>${m}</sup> × ${nvec})</h3>`;
      pasosHTML += matrixToTable(A, "Matriz inicial");

      const {R, rank, pivotCols, snapshots} = rrefWithSteps(A);

      snapshots.forEach((s, idx) => {
        pasosHTML += `<div class="op"><b>Paso ${idx+1}:</b> ${s.op}</div>`;
        pasosHTML += matrixToTable(s.mat);
      });

      pasosHTML += `<h3>Matriz reducida (RREF)</h3>`;
      pasosHTML += matrixToTable(R, "RREF");

      const generaRn = (rank === m);
      const indepCols = pivotCols.map(j => j + 1);
      let resumenHTML = `<div class="badge">Vectores: ${nvec}</div>`;
      resumenHTML += `<div class="badge">Dimensión: ${m}</div>`;
      resumenHTML += `<div class="badge">Rango: ${rank}</div>`;
      resumenHTML += `<div class="badge ${generaRn ? "ok" : "no"}">${generaRn ? `Genera R^${m}` : `No genera R^${m}`}</div>`;
      resumenHTML += `<p><b>Columnas pivote:</b> ${indepCols.join(", ") || "ninguna"}.</p>`;
      resumenHTML += generaRn ? `<p class="text-ok">✅ Sí es generador.</p>` : `<p class="text-no">❌ No es generador.</p>`;

      resumenDiv.innerHTML = resumenHTML;
      pasosDiv.innerHTML = pasosHTML;
      resumenDiv.style.display = "block";
      pasosDiv.style.display = "block";
    } catch (err) {
      resumenDiv.innerHTML = `<div class="op">Error: ${err.message}</div>`;
      resumenDiv.style.display = "block";
    }
  });
});
