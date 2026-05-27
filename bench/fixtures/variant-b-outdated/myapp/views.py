from asgiref.sync import sync_to_async
from django.http import JsonResponse
from .models import Product


def _get_products():
    return list(Product.objects.all().values("id", "name"))


async def product_list(request):
    products = await sync_to_async(_get_products)()
    return JsonResponse({"products": products})


async def product_detail(request, pk):
    get_product = sync_to_async(Product.objects.get)
    product = await get_product(pk=pk)
    return JsonResponse({"id": product.id, "name": product.name})
