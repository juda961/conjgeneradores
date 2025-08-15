document.addEventListener("DOMContentLoaded", () => {
  const ta = document.getElementById("vectores");
  const btn = document.getElementById("btn-comprobar");
  const resumenDiv = document.getElementById("resumen");
  const pasosDiv = document.getElementById("pasos");
  const modoNumber = document.getElementById("modoNumber");
  const precisionInput = document.getElementById("precision");

  // Helpers numéricos
  const fmt = (x) => {
    const mode = modoNumber.value;
    const prec = Math.max(1, Math.min(12, parseInt(precisionInput.value || "6", 10)));
    if (!isFinite(x)) return x > 0 ? "∞" : (x < 0 ? "−∞" : "NaN");
    if (mode === "fraction") {
      try {
        return math.fraction(x).toString();
      } catch {
        return Number(x).toFixed(prec);
      }
    }
    return Number(x).toFixed(prec);
  };

  // Parsea textarea en matriz con vectores como columnas
  function parseVectors(text) {
    const lines = text
      .split("\n")
      .map(s => s.trim())
      .filter(s => s.length > 0);

    if (lines.length === 0) throw new Error("No ingresaste vectores.");

    // Convertir cada línea en array de números (permitir comas o espacios)
    const cols = lines.map(line => {
      const parts = line.includes(",")
        ? line.split(",")
        : line.split(/\s+/);
      const nums = parts.map(p => {
        const v = Number(p.trim());
        if (!isFinite(v)) throw new Error("Hay componentes no numéricas.");
        return v;
      });
      return nums;
    });

    // Igualar longitudes con validación
    const n = cols[0].length;
    cols.forEach((c, i) => {
      if (c.length !== n) {
        throw new Error(`Todos los vectores deben tener la misma cantidad de componentes. La línea ${i+1} tiene ${c.length} y se esperaba ${n}.`);
      }
    });

    // Convertir a matriz con columnas = vectores (matriz m x nvec)
    // m = dimensión del espacio (componentes), nvec = cantidad de vectores
    const m = n;             // componentes
    const nvec = cols.length;
    const A = Array.from({length: m}, () => Array(nvec).fill(0));
    for (let j = 0; j < nvec; j++) {
      for (let i = 0; i < m; i++) {
        A[i][j] = cols[j][i];
      }
    }
    return { A, m, nvec, cols };
  }

  // Copia profunda
  const clone = (M) => M.map(r => r.slice());

  // Imprime matriz como tabla HTML
  function matrixToTable(M, headerLabel = "") {
    let html = `<table class="tabla">`;
    if (headerLabel) {
      html += `<thead><tr><th colspan="${M[0].length}">${headerLabel}</th></tr></thead>`;
    }
    html += `<tbody>`;
    for (const row of M) {
      html += `<tr>`;
      for (const val of row) {
        html += `<td>${fmt(val)}</td>`;
      }
      html += `</tr>`;
    }
    html += `</tbody></table>`;
    return html;
  }

  // RREF con pasos (operaciones elementales y matrices intermedias)
  function rrefWithSteps(M) {
    const A = clone(M);
    const rows = A.length;
    const cols = A[0].length;
    let r = 0; // fila del pivote
    const ops = [];
    const snapshots = [];

    function pushSnap(opText) {
      snapshots.push({ op: opText, mat: clone(A) });
    }

    for (let c = 0; c < cols && r < rows; c++) {
      // 1) Buscar pivote (máximo en |.| para estabilidad simple)
      let piv = r;
      for (let i = r + 1; i < rows; i++) {
        if (Math.abs(A[i][c]) > Math.abs(A[piv][c])) piv = i;
      }
      if (Math.abs(A[piv][c]) < 1e-12) continue; // columna sin pivote

      // 2) Intercambio si es necesario
      if (piv !== r) {
        [A[piv], A[r]] = [A[r], A[piv]];
        ops.push(`R${r+1} ↔ R${piv+1}`);
        pushSnap(`Intercambia filas R${r+1} y R${piv+1}`);
      }

      // 3) Normalizar fila pivote a 1
      const pivVal = A[r][c];
      if (Math.abs(pivVal - 1) > 1e-12) {
        for (let j = 0; j < cols; j++) A[r][j] /= pivVal;
        ops.push(`R${r+1} := (1/${fmt(pivVal)})·R${r+1}`);
        pushSnap(`Normaliza pivote en columna ${c+1}`);
      }

      // 4) Eliminar en otras filas
      for (let i = 0; i < rows; i++) {
        if (i === r) continue;
        const factor = A[i][c];
        if (Math.abs(factor) > 1e-12) {
          for (let j = 0; j < cols; j++) {
            A[i][j] -= factor * A[r][j];
          }
          ops.push(`R${i+1} := R${i+1} − (${fmt(factor)})·R${r+1}`);
          pushSnap(`Elimina en fila ${i+1} usando pivote de la columna ${c+1}`);
        }
      }

      r++; // siguiente fila de pivote
    }

    // Identificar columnas pivote (buscando 1s únicos por columna)
    const pivotCols = [];
    for (let c = 0; c < cols; c++) {
      let countOnes = 0, rowOne = -1, anyOther = false;
      for (let i = 0; i < rows; i++) {
        if (Math.abs(A[i][c] - 1) < 1e-10) { countOnes++; rowOne = i; }
        else if (Math.abs(A[i][c]) > 1e-10) { anyOther = true; }
      }
      if (countOnes === 1 && !anyOther) pivotCols.push(c);
    }

    return { R: A, rank: pivotCols.length, pivotCols, ops, snapshots };
  }

  // Principal
  btn.addEventListener("click", () => {
    resumenDiv.style.display = "none";
    pasosDiv.style.display = "none";
    resumenDiv.innerHTML = "";
    pasosDiv.innerHTML = "";

    try {
      const { A, m, nvec, cols } = parseVectors(ta.value);

      // Mostrar matriz inicial
      let pasosHTML = `<h3>Matriz con vectores como columnas (R<sup>${m}</sup> × ${nvec})</h3>`;
      pasosHTML += matrixToTable(A, "Matriz inicial");

      // RREF + pasos
      const { R, rank, pivotCols, ops, snapshots } = rrefWithSteps(A);

      // Mostrar pasos
      if (snapshots.length === 0) {
        pasosHTML += `<div class="op">No hubo operaciones (ya estaba reducida).</div>`;
      } else {
        snapshots.forEach((s, idx) => {
          pasosHTML += `<div class="op"><b>Paso ${idx+1}:</b> ${s.op}</div>`;
          pasosHTML += matrixToTable(s.mat);
        });
      }

      pasosHTML += `<h3>Matriz reducida (RREF)</h3>`;
      pasosHTML += matrixToTable(R, "RREF");

      // Conclusiones
      const generaRn = (rank === m);
      const indepCols = pivotCols.map(j => j+1); // 1-index
      const resumen = `
        <div class="badge">Vectores: ${nvec}</div>
        <div class="badge">Dimensión del espacio: ${m}</div>
        <div class="badge">Rango (dim. del span): ${rank}</div>
        <div class="badge ${generaRn ? "ok" : "no"}">
          ${generaRn ? "Genera R^" + m : "No genera R^" + m}
        </div>
        <p><b>Columnas pivote:</b> ${indepCols.length ? indepCols.join(", ") : "ninguna"} (de la matriz original).<br>
        Esto significa que los vectores <b>${indepCols.length ? indepCols.join(", ") : "—"}</b> forman una base del subespacio generado.</p>
        ${generaRn
          ? `<p class="text-ok">✅ El conjunto <b>sí</b> es generador de R<sup>${m}</sup>.</p>`
          : `<p class="text-no">❌ El conjunto <b>no</b> genera R<sup>${m}</sup>. Su span tiene dimensión ${rank}.</p>`
        }
      `;

      resumenDiv.innerHTML = resumen;
      pasosDiv.innerHTML = pasosHTML;

      resumenDiv.style.display = "block";
      pasosDiv.style.display = "block";
    } catch (err) {
      resumenDiv.innerHTML = `Error: ${err.message}`;
      resumenDiv.style.display = "block";
    }
  });
});
