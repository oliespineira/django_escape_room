from django.db import models

# Create your models here.


class Player(models.Model):
    EXPERIENCE_CHOICES =[
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('expert', 'Expert'),
    ]
    HINT_CHOICES = [
        ('none', 'No hints'),
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('frequent', 'Frequent'),
    ]

    name = models.CharField(max_length=100)
    experience_level= models.CharField(max_length=20, choices=EXPERIENCE_CHOICES)
    hint-preference=models.CharField(max_length=20, choices=HINT_CHOICES)

    def __str__(self):
        return self.name

class Team(models.Model):
    name = models.CharField(max_length=100)
    players =models.ManyToManyField(Player)
    created_at = models.DateTimeField(aouto_now_add= True)

    def __str__(self):
        return self.name
    
class EscapeRoom(models.Model):
    DIFFICULTY_CHOICES =[
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]

    name= models.CharField(max_length=100)
    description= models.TextField()
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES)
    max_time = models.IntegerField() #in minutes
    theme = models.CharField(max_length=100)

    def __str__(self):
        return self.name
    
class Puzzle(models.Model):
    room = models.ForeignKey(EscapeRoom, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField()
    difficulty = models.IntegerField(default=5)
    expected_time = models.IntegerField()  #in seconds
    order = models.IntegerField()

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.room.name} - {self.name}"
    

class GameSession(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    room = models.ForeignKey(EscapeRoom, on_delete=models.CASCADE)

    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)

    success = models.BooleanField(null=True, blank=True)
    active = models.BooleanField(default=True)

    current_puzzle = models.ForeignKey(Puzzle, on_delete=models.SET_NULL, null=True, blank=True)

    last_hint_time = models.DateTimeField(null=True, blank=True)
    hints_given = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.team.name} in {self.room.name}"
    
class PuzzleAttempt(models.Model):
    session = models.ForeignKey(GameSession, on_delete=models.CASCADE)
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE)

    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)

    hints_used = models.IntegerField(default=0)
    completed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.session.team.name} - {self.puzzle.name}"

class HintEvent(models.Model):
    session = models.ForeignKey(GameSession, on_delete=models.CASCADE)
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE)

    timestamp = models.DateTimeField(auto_now_add=True)

    auto_suggested = models.BooleanField(default=False)
    accepted = models.BooleanField(default=False)

    hint_text = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Hint for {self.session.team.name} at {self.timestamp}"