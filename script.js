function calcularLHopital() {
    const fx = document.getElementById("fx").value;
    const gx = document.getElementById("gx").value;
    const x0 = parseFloat(document.getElementById("x0").value);
    const resultadoDiv = document.getElementById("resultado-lhopital");

    try {
        const df = math.derivative(fx, 'x').toString();
        const dg = math.derivative(gx, 'x').toString();
        const num = math.evaluate(df, { x: x0 });
        const den = math.evaluate(dg, { x: x0 });

        let resultado;
        if (den === 0) {
            resultado = "Indeterminado";
        } else {
            const valor = num / den;
            if (!isFinite(valor)) {
                resultadoDiv.innerHTML = valor > 0 ? "→ +∞" : "→ -∞";
                resultadoDiv.classList.add("infinito");
                return;
            }
            resultado = valor.toFixed(6);
        }

        resultadoDiv.innerHTML = `Límite según L'Hôpital = ${resultado}`;
        resultadoDiv.classList.remove("infinito");
    } catch (error) {
        resultadoDiv.innerHTML = "Error en la expresión";
    }
}

function calcularDerivada() {
    const funcion = document.getElementById("f-deriv").value;
    const resultadoDiv = document.getElementById("resultado-derivada");

    try {
        const derivada = math.derivative(funcion, 'x').toString();
        resultadoDiv.innerHTML = `Derivada: ${derivada}`;
        resultadoDiv.classList.remove("infinito");
    } catch (error) {
        resultadoDiv.innerHTML = "Error en la expresión";
    }
}
