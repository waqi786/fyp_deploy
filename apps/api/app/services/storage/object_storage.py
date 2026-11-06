from dataclasses import dataclass, field


@dataclass
class StoredObject:
    object_name: str
    content_type: str
    data: bytes


@dataclass
class ObjectStorageService:
    bucket_name: str = "resora-figures"
    objects: dict[str, StoredObject] = field(default_factory=dict)

    def put_bytes(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.objects[object_name] = StoredObject(object_name=object_name, content_type=content_type, data=data)
        return f"s3://{self.bucket_name}/{object_name}"

    def get_bytes(self, object_name: str) -> bytes | None:
        obj = self.objects.get(object_name)
        return obj.data if obj else None
