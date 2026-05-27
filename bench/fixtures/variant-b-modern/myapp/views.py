from django.http import JsonResponse
from .models import Product


async def product_list(request):
    products = []
    async for p in Product.objects.all():
        products.append({"id": p.id, "name": p.name})
    return JsonResponse({"products": products})


async def product_detail(request, pk):
    product = await Product.objects.aget(pk=pk)
    return JsonResponse({"id": product.id, "name": product.name})
