namespace InvoiceExtractWebApi.Model
{
    public class ItemInvoice
    {
        public string? Code { get; set; }
        public string? Description { get; set; }
        public decimal Quantity { get; set; }
        public string? Unity { get; set; }
        public decimal Value { get; set; }
    }
}
