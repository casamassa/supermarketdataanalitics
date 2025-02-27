using MongoDB.Bson.Serialization.Attributes;
using MongoDB.Bson;

namespace InvoiceExtractWebApi.Model
{
    public class Invoice
    {
        [BsonId]
        [BsonRepresentation(BsonType.ObjectId)]
        public string? Id { get; set; }

        public string? MarketName { get; set; }

        public DateTime InvoiceDate { get; set; }

        public decimal TotalInvoice { get; set; }

        public int QuantityTotalItems { get; set; }

        public string? AccessKey { get; set; }

        public List<ItemInvoice>? Items { get; set; }
    }
}
