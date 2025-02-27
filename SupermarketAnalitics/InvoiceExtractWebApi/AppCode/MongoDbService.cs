using InvoiceExtractWebApi.Model;
using MongoDB.Driver;

namespace InvoiceExtractWebApi.AppCode
{
    public class MongoDbService
    {
        private readonly IMongoCollection<Invoice> _invoicesCollection;

        public MongoDbService(IConfiguration configuration)
        {
            var connectionString = configuration.GetConnectionString("MongoDB");
            var databaseName = configuration["MongoDB:Database"];
            var collectionName = configuration["MongoDB:Collection"];

            var client = new MongoClient(connectionString);
            var database = client.GetDatabase(databaseName);
            _invoicesCollection = database.GetCollection<Invoice>(collectionName);
        }

        public async Task SaveInvoiceAsync(Invoice invoice)
        {
            var existingInvoice = await _invoicesCollection.Find(i => i.AccessKey == invoice.AccessKey).FirstOrDefaultAsync();

            if (existingInvoice == null)
            {
                await _invoicesCollection.InsertOneAsync(invoice);
            }
        }
    }
}