from django.contrib import admin
from .models import *

admin.site.register(Player)
admin.site.register(Team)
admin.site.register(EscapeRoom)
admin.site.register(Puzzle)
admin.site.register(GameSession)
admin.site.register(PuzzleAttempt)
admin.site.register(HintEvent)


