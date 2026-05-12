import contextvars

# Variable globale pour stocker l'année académique courante pour le thread/contexte actuel
_current_academic_year_id = contextvars.ContextVar('current_academic_year_id', default=None)

class AcademicYearMiddleware:
    """
    Middleware qui capture le header 'X-Academic-Year' et le stocke 
    dans un ContextVar pour qu'il soit accessible partout dans le code.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        academic_year_id = request.headers.get('X-Academic-Year')
        
        # Stockage de l'ID
        token = _current_academic_year_id.set(academic_year_id)
        
        try:
            response = self.get_response(request)
        finally:
            # Nettoyage après la réponse
            _current_academic_year_id.reset(token)
            
        return response

def get_current_academic_year_id():
    return _current_academic_year_id.get()
