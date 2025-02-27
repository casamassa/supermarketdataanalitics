namespace InvoiceExtractWebApi.Model
{
    public class Invoice
    {
        public string? MarketName { get; set; }

        public DateTime InvoiceDate { get; set; }

        public decimal TotalInvoice { get; set; }

        public int QuantityTotalItems { get; set; }

        public string? AccessKey { get; set; }

        public List<ItemInvoice>? Items { get; set; }
    }
}
