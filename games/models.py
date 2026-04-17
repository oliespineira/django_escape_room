from django.db import models
from django.utils import timezone

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
    hint_preference=models.CharField(max_length=20, choices=HINT_CHOICES)

    def __str__(self):
        return self.name

class Team(models.Model):
    name = models.CharField(max_length=100)
    players =models.ManyToManyField(Player)
    created_at = models.DateTimeField(auto_now_add= True)

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
    CATEGORY_CHOICES = [
        ('logical',  'Logical'),
        ('physical', 'Physical'),
        ('code',     'Code-breaking'),
        ('search',   'Search & discovery'),
    ]

    room = models.ForeignKey(EscapeRoom, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='logical')
    subtype = models.CharField(max_length=50, blank=True, default='')
    difficulty = models.IntegerField(default=5)
    expected_time = models.IntegerField()
    order = models.IntegerField()
    is_parallel = models.BooleanField(default=False)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.room.name} - {self.name}"
    

class GameSession(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    room = models.ForeignKey(EscapeRoom, on_delete=models.CASCADE)

    start_time = models.DateTimeField(null=True, blank=True)  # before this was auto and now it is only filled out when GM presses Start
    end_time = models.DateTimeField(null=True, blank=True)

    success = models.BooleanField(null=True, blank=True)
    active = models.BooleanField(default=False)  #  session doesn't begin until GM presses start
    paused_at = models.DateTimeField(null=True, blank=True)  # moments when sessioned paused
    paused_duration = models.IntegerField(default=0)  # seconds accumulated during the pause

    current_puzzle = models.ForeignKey(Puzzle, on_delete=models.SET_NULL, null=True, blank=True)

    last_hint_time = models.DateTimeField(null=True, blank=True)
    hints_given = models.IntegerField(default=0)

    STATUS_PENDING = 'pending'
    STATUS_ACTIVE  = 'active'
    STATUS_PAUSED  = 'paused'
    STATUS_ENDED   = 'ended'

    @property
    def status(self):
        if self.end_time:
            return self.STATUS_ENDED
        if self.paused_at:
            return self.STATUS_PAUSED
        if self.start_time:
            return self.STATUS_ACTIVE
        return self.STATUS_PENDING

    @property
    def elapsed_seconds(self):
        """Tiempo real transcurrido, descontando pausas."""
        if not self.start_time:
            return 0
        end = self.end_time or (self.paused_at if self.paused_at else timezone.now())
        total = (end - self.start_time).total_seconds()
        return max(0, int(total - self.paused_duration))

    def __str__(self):
        return f"{self.team.name} in {self.room.name}"
    
class PuzzleAttempt(models.Model):
    session = models.ForeignKey(GameSession, on_delete=models.CASCADE)
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE)

    start_time = models.DateTimeField(default=timezone.now)
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


class PuzzleOutput(models.Model):
    OUTPUT_TYPES = [
        ("code", "Numeric/text code"),
        ("key", "Physical key"),
        ("item", "Item or object"),
        ("info", "Information / clue"),
    ]

    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE, related_name="outputs")
    output_type = models.CharField(max_length=20, choices=OUTPUT_TYPES)
    output_value = models.CharField(max_length=100)
    label = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.puzzle.name} -> {self.label}"


class PuzzleDependency(models.Model):
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE, related_name="dependencies")
    requires_output = models.ForeignKey(
        PuzzleOutput, on_delete=models.CASCADE, related_name="unlocks"
    )
    all_required = models.BooleanField(default=True)

    class Meta:
        unique_together = ("puzzle", "requires_output")

    def __str__(self):
        return f"{self.puzzle.name} requires [{self.requires_output.label}]"


class OutputAcquired(models.Model):
    session = models.ForeignKey(
        GameSession, on_delete=models.CASCADE, related_name="acquired_outputs"
    )
    output = models.ForeignKey(PuzzleOutput, on_delete=models.CASCADE)
    acquired_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("session", "output")

    def __str__(self):
        return f"{self.session} acquired {self.output.label}"