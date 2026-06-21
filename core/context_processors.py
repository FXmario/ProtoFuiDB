from Databases.models import Database


def databases_context(request):
    if request.user.is_authenticated:
        return {"databases": Database.objects.filter(owner=request.user)}
    return {"databases": Database.objects.none()}