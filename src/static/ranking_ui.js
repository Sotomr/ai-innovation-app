// Función para mejorar la experiencia de ranking
document.addEventListener('DOMContentLoaded', function() {
    // Buscar el botón de ranking
    const rankingButtons = document.querySelectorAll('button:not([id]):not([class])');
    rankingButtons.forEach(btn => {
        if (btn.textContent && btn.textContent.includes('Generar Ranking')) {
            setupRankingButton(btn);
        }
    });

    // También buscar por clases específicas que puedan ser añadidas
    const specificButtons = document.querySelectorAll('.generate-ranking-btn, button[id*="ranking"]');
    specificButtons.forEach(btn => {
        setupRankingButton(btn);
    });

    function setupRankingButton(btn) {
        const originalText = btn.textContent;
        
        btn.addEventListener('click', function() {
            // Mostrar estado de carga
            btn.textContent = '⏳ Generando ranking...';
            btn.disabled = true;
            
            // Buscar el elemento de estado más cercano
            const statusElements = document.querySelectorAll('div[id*="status"], div[class*="status"], p[class*="status"]');
            statusElements.forEach(element => {
                if (element.textContent.includes('Esperando') || element.textContent.includes('estado') || !element.textContent) {
                    element.textContent = 'Procesando ideas y generando ranking. Este proceso puede tardar unos minutos...';
                }
            });
            
            // Restaurar el botón después de un tiempo máximo (2 minutos)
            setTimeout(() => {
                if (btn.textContent.includes('Generando')) {
                    btn.textContent = originalText;
                    btn.disabled = false;
                }
            }, 120000);
        });
    }
    
    // Observar cambios en la interfaz para detectar cuando el ranking está completo
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'childList' && mutation.addedNodes.length) {
                mutation.addedNodes.forEach(node => {
                    // Restaurar botones de ranking si hay un resultado
                    if (node.nodeType === 1 && (node.innerHTML?.includes('Ranking generado con éxito') || 
                       node.textContent?.includes('Ranking generado con éxito'))) {
                        // Restaurar todos los botones de ranking
                        document.querySelectorAll('button').forEach(btn => {
                            if (btn.textContent && btn.textContent.includes('Generando ranking')) {
                                btn.textContent = 'Generar Ranking';
                                btn.disabled = false;
                            }
                        });
                    }
                });
            }
        });
    });
    
    // Observar cambios en todo el documento
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
});
