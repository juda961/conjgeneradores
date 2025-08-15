function calcularLHopital() {
    const fx = document.getElementById("fx").value;
    const gx = document.getElementById("gx").value;
    const x0 = parseFloat(document.getElementById("x0").value);

    try {
        const dfx = math.derivative(fx, 'x').toString();
        const dgx = math.derivative(gx, 'x').toString();

        const num = math.evaluate(dfx, { x: x0 });
        const den = math.evaluate(dgx, { x: x0 });

        let resultado = num / den;
        const resDiv = document.getElementById("resultado-lhopital");

        if (!isFinite(resultado)) {
            resDiv.innerHTML = resultado > 0 ? "∞ (tiende a +∞)" : "∞ (tiende a -∞)";
            resDiv.className = "resultado infinito";
        } else {
            resDiv.innerHTML = "Límite según L'Hôpital = " + resultado;
            resDiv.className = "resultado";
        }
    } catch (err) {
        document.getElementById("resultado-lhopital").innerHTML = "Error: " + err.message;
    }
}

function calcularDerivada() {
    const f = document.getElementById("f-deriv").value;
    try {
        const deriv = math.derivative(f, 'x').toString();
        document.getElementById("resultado-derivada").innerHTML = "Derivada: " + deriv;
    } catch (err) {
        document.getElementById("resultado-derivada").innerHTML = "Error: " + err.message;
    }
}
