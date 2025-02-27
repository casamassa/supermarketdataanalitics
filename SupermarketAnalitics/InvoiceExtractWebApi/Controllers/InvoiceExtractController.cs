using InvoiceExtractWebApi.AppCode;
using InvoiceExtractWebApi.Model;
using Microsoft.AspNetCore.Mvc;
using System.Net;
using System.Text.RegularExpressions;

namespace InvoiceExtractWebApi.Controllers
{
    [ApiController]
    [Route("[controller]")]
    public class InvoiceExtractController : ControllerBase
    {
        private readonly ILogger<InvoiceExtractController> _logger;

        public InvoiceExtractController(ILogger<InvoiceExtractController> logger)
        {
            _logger = logger;
        }

        [HttpGet("")]
        public IActionResult Index(string qrCodeParameter)
        {
            /* Some examples URL's
            https://portalsped.fazenda.mg.gov.br/portalnfce/sistema/qrcode.xhtml?p=31250204641376021486650640001334691832214190|2|1|1|1308AB30650940E1EA488E7423E5898A8BF323BB
            https://portalsped.fazenda.mg.gov.br/portalnfce/sistema/qrcode.xhtml?p=31250204641376021486650660001283271808280606|2|1|1|A7DE2D334A70FFC1258D7CE336891397AF0A24E1
            https://portalsped.fazenda.mg.gov.br/portalnfce/sistema/qrcode.xhtml?p=31250204641376021486650680001118761253118381|2|1|1|E84ECC33F2A328B8ACE4B7EC12443FFCF968B3DE
            */
            
            var url = $"https://portalsped.fazenda.mg.gov.br/portalnfce/sistema/qrcode.xhtml?p={qrCodeParameter}";

            var invoice = new Invoice();
            using (var client = new WebClient())
            {
                var urlResult = client.DownloadString(url);
                
                var marketNameRegex = new Regex(@"<th\s+class=""text-center text-uppercase"">\s*<H4>\s*<b>(.*?)</b>\s*</H4>\s*</th>");
                var marketName = marketNameRegex.Match(urlResult).Groups[1].Value;
                invoice.MarketName = marketName;

                var invoiceDateRegex = new Regex(@"<td>(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})</td>");
                var invoiceDateStr = invoiceDateRegex.Match(urlResult).Groups[1].Value;
                invoice.InvoiceDate = Convert.ToDateTime(invoiceDateStr);

                var totalInvoiceRegex = new Regex(@"<div\s+class=""col-lg-2"">\s*<strong>(\d+\.\d{2})</strong>\s*</div>");
                var totalInvoiceStr = totalInvoiceRegex.Match(urlResult).Groups[1].Value;
                invoice.TotalInvoice = decimal.Parse(totalInvoiceStr, System.Globalization.CultureInfo.InvariantCulture);

                var quantityTotalItemsRegex = new Regex(@"<div\s+class=""col-lg-2"">\s*<strong>(\d+)</strong>\s*</div>");
                var quantityTotalItemsStr = quantityTotalItemsRegex.Match(urlResult).Groups[1].Value;
                invoice.QuantityTotalItems = Convert.ToInt32(quantityTotalItemsStr);

                var accessKeyRegex = new Regex(@"<td[^>]*>([\d\-\/\.]+)</td>");
                var accessKey = accessKeyRegex.Match(urlResult).Groups[1].Value;
                invoice.AccessKey = accessKey;

                invoice.Items = InvoiceScraper.ExtractItems(urlResult);
            }

            return Ok(invoice);
        }
    }
}
