---
id: django-async-views
title: Use Native Async Views Instead of sync_to_async Wrappers
category: django
layer: 2
tags:
  - django
  - async
  - views
  - orm
aliases:
  - sync-to-async
  - async-orm
python: ">=3.9"
frequency: medium
detect-patterns:
  - "from asgiref\.sync import sync_to_async"
---

# Use Native Async Views

Write async views with `async def` and use Django's async ORM methods (`aget`, `acreate`, etc.) and `async for` iteration instead of wrapping synchronous code with `sync_to_async`.

## BAD

```python
from asgiref.sync import sync_to_async
from django.http import JsonResponse

def get_user(request, user_id):
    user = User.objects.get(id=user_id)
    orders = list(Order.objects.filter(user=user).select_related("product"))
    return JsonResponse({"user": user.name, "orders": len(orders)})

# or wrapping sync code:
async def get_user_async(request, user_id):
    user = await sync_to_async(User.objects.get)(id=user_id)
    return JsonResponse({"user": user.name})
```

## GOOD

```python
from django.http import JsonResponse

async def get_user(request, user_id):
    user = await User.objects.aget(id=user_id)
    orders = [o async for o in Order.objects.filter(user=user).select_related("product")]
    return JsonResponse({"user": user.name, "orders": len(orders)})
```

## Why

- Native async views avoid the thread-pool overhead of `sync_to_async`
- Async ORM methods (`aget`, `acreate`, `aupdate`, etc.) and `async for` iteration run queries without blocking the event loop
- `async for` on querysets streams results without materializing the full list
- Cleaner code without `sync_to_async` wrapper boilerplate

## Version Notes

- Django 3.1+: async view support (but ORM calls still require `sync_to_async`)
- Django 4.1+: async ORM methods (`aget`, `acreate`, `aupdate`, `adelete`, etc.)
- Django 5.0+: expanded async queryset support (`aiterator`, `aexists`, etc.)
- For Django 3.1-4.0, `sync_to_async` wrappers remain the correct approach

## References

- [Django Async Support](https://docs.djangoproject.com/en/5.2/topics/async/)
- [Django 4.1 Async ORM](https://docs.djangoproject.com/en/5.2/releases/4.1/#asynchronous-orm-interface)
