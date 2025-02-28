using HtmlAgilityPack;
using InvoiceExtractWebApi.Model;
using System.Text.RegularExpressions;

namespace InvoiceExtractWebApi.AppCode
{
    public class InvoiceScraper
    {
        public static List<ItemInvoice> ExtractItems(string html)
        {
            var items = new List<ItemInvoice>();

            var doc = new HtmlDocument();
            doc.LoadHtml(html);

            // Seleciona todas as linhas <tr> dentro da <tbody id="myTable">
            var rows = doc.DocumentNode.SelectNodes("//tbody[@id='myTable']/tr");

            if (rows != null)
            {
                foreach (var row in rows)
                {
                    var columns = row.SelectNodes("td");

                    if (columns != null && columns.Count == 4)
                    {
                        // Regex para extrair dados
                        var descMatch = Regex.Match(columns[0].InnerText, @"(.*?)\s*\(Código:\s*(\d+)\)");
                        var quantityMatch = Regex.Match(columns[1].InnerText, @"Qtde total de ítens:\s*([\d,.]+)");
                        var unitMatch = Regex.Match(columns[2].InnerText, @"UN:\s*(\w+)");
                        var valueMatch = Regex.Match(columns[3].InnerText, @"Valor total R\$:\s*R?\$?\s*([\d,.]+)");

                        if (descMatch.Success && quantityMatch.Success && unitMatch.Success && valueMatch.Success)
                        {
                            var item = new ItemInvoice
                            {
                                Description = descMatch.Groups[1].Value.Trim(),
                                Code = descMatch.Groups[2].Value.Trim(),
                                Quantity = decimal.Parse(quantityMatch.Groups[1].Value.Replace(",", ""), System.Globalization.CultureInfo.InvariantCulture),
                                Unit = unitMatch.Groups[1].Value.Trim(),
                                Value = decimal.Parse(valueMatch.Groups[1].Value.Replace(".", "").Replace(",", "."), System.Globalization.CultureInfo.InvariantCulture)
                            };

                            items.Add(item);
                        }
                    }
                }
            }

            return items;
        }
    }
}
