from organica.lib.library import Library
from organica.lib.objects import TagValue


def buildSample():
    lib = Library.createLibrary(':memory:')

    # create tag classes
    author_class = lib.createTagClass('author')
    publisher_class = lib.createTagClass('publisher')
    publish_year_class = lib.createTagClass('publish_year', TagValue.TYPE_NUMBER)
    page_count_class = lib.createTagClass('page_count', TagValue.TYPE_NUMBER)
    gentre_class = lib.createTagClass('gentre')

    alice_book = lib.createNode('Alice in Wonderland')
    alice_book.link(author_class, 'Lewis Carrol')
    alice_book.link(publisher_class, 'Ferguson')
    alice_book.link(publish_year_class, 1992)
    alice_book.link(page_count_class, 89)
    alice_book.link(gentre_class, 'Fiction')
    alice_book.flush(lib)

    romeo_book = lib.createNode('Romeo and Juliet')
    romeo_book.link(author_class, 'William Shakespeare')
    romeo_book.link(publisher_class, 'G. Graebner')
    romeo_book.link(publish_year_class, 1859)
    romeo_book.link(page_count_class, 100)
    romeo_book.link(gentre_class, 'Tragedy')
    romeo_book.flush(lib)

    crime_book = lib.createNode('Crime and Punishment')
    crime_book.link(author_class, 'Feodor Dostoevsky')
    crime_book.link(publisher_class, 'Walter Scott Pub. Co')
    crime_book.link(publish_year_class, 1910)
    crime_book.link(page_count_class, 455)
    crime_book.link(gentre_class, 'Novel')
    crime_book.flush(lib)

    snark_book = lib.createNode('The Hunting of the Snark')
    snark_book.link(author_class, 'Lewis Carrol')
    snark_book.link(publisher_class, 'I. E. Clark Publications')
    snark_book.link(publish_year_class, 1987)
    snark_book.link(page_count_class, 29)
    snark_book.link(gentre_class, 'Fiction')
    crime_book.flush(lib)

    return lib
