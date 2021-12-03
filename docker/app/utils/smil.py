from abc import abstractmethod, ABC
from collections import MutableSequence
from datetime import datetime
from re import search

from isodate import parse_datetime
from lxml import etree


NSMAP = {None: "http://www.w3.org/2001/SMIL20/Language"}


def _stripwallclock(s):
    match = search("wallclock\\((.*)\\)", s)
    if match:
        return match.group(1)
    else:
        return s


def parse(xml):
    """
    Parse function, does an initial read to figure out the root element then
    attempts to call the relevant parser
    """
    if isinstance(xml, (str, bytes)):
        xml = etree.fromstring(xml)
    if not isinstance(xml, etree._Element):
        raise TypeError("not valid xml")

    tag = etree.QName(xml).localname

    return TAGMAP[tag].parse(xml)


class SMILBase(ABC):
    """SMILBase

    Base SMIL object to handle shared functionality
    """

    def __lt__(self, other):
        return str(self).__lt__(str(other))

    def __le__(self, other):
        return str(self).__le__(str(other))

    def __gt__(self, other):
        return str(self).__gt__(str(other))

    def __ge__(self, other):
        return str(self).__ge__(str(other))

    def __eq__(self, other):
        return str(self).__eq__(str(other))

    def __repr__(self):
        props = {
            p: repr(getattr(self, p))
            for p in dir(type(self))
            if isinstance(getattr(type(self), p), property)
        }

        return "{name}({prop})".format(
            name=type(self).__name__,
            prop=", ".join(
                ["{k}={v}".format(k=k, v=v) for k, v in props.items()]
            ),
        )

    def __str__(self):
        return str(bytes(self), "UTF-8",)

    def __bytes__(self):
        return etree.tostring(
            self.element(),
            pretty_print=True,
            xml_declaration=True,
            encoding="UTF-8",
        )

    @abstractmethod
    def element(self):
        pass

    @abstractmethod
    def parse(self):
        pass


class SMILListBase(MutableSequence, SMILBase):
    """SMILListBase

    Base object for lists
    """

    def __init__(self, *args, **kwargs):
        self._list = list()
        self.list = list()
        if len(args) == 1 and len(kwargs) == 0 and isinstance(args[0], list):
            self.extend(args[0])
        elif (
            len(args) == 0
            and len(kwargs) == 1
            and "list" in kwargs
            and isinstance(kwargs["list"], list)
        ):
            self.extend(kwargs["list"])
        else:
            self.extend(list(args))

    def __len__(self):
        return len(self.list)

    def __getitem__(self, index):
        return self.list[index]

    def __setitem__(self, index, value):
        self.check(value)
        self.list[index] = value

    def __delitem__(self, index):
        del self.list[index]

    def insert(self, index, value):
        self.check(value)
        self.list.insert(index, value)

    @property
    def list(self):
        return self._list

    @list.setter
    def list(self, l):
        if not isinstance(l, list):
            raise TypeError("must be a list")
        elif all([self.check(x) for x in l]):
            self._list = l


class SMIL(SMILBase):
    """SMIL object

    Currently only supports fairly limited single list of items within a seq
    for the body and a list of meta elements for the head
    """

    def __init__(self, body=None, head=None):
        if body:
            self.body = body
        else:
            self.body = []
        if head:
            self.head = head
        else:
            self.head = []

    # map general MutableSequence methods to body
    def __len__(self):
        return self.body.__len__()

    def __getitem__(self, index):
        return self.body.__getitem__(index)

    def __setitem__(self, index, value):
        self.body.__setitem__(index, value)

    def __delitem__(self, index):
        self.body.__delitem__(index)

    def insert(self, index, value):
        self.body.insert(index, value)

    def append(self, value):
        self.body.append(value)

    # properties
    @property
    def body(self):
        return self._body

    @body.setter
    def body(self, l):
        if isinstance(l, Seq):
            self._body = l
        elif isinstance(l, list):
            self._body = Seq(l)
        else:
            raise TypeError("must be a list or Seq")

    @property
    def head(self):
        return self._head

    @head.setter
    def head(self, l):
        if isinstance(l, Head):
            self._head = l
        elif isinstance(l, list):
            self._head = Head(l)
        else:
            raise TypeError("must be a list or Head")

    def element(self):
        el = etree.Element("smil", nsmap=NSMAP)
        head = etree.Element("head")
        if self.head:
            for element in self.head:
                head.append(element.element())
        el.append(head)
        body = etree.Element("body")
        if self.body:
            body.append(self.body.element())
        el.append(body)

        return el

    @staticmethod
    def parse(xml):
        """Parse XML to a SMIL object"""
        if isinstance(xml, (str, bytes)):
            xml = etree.fromstring(xml)

        new_smil = SMIL()

        for element in xml.find("head", xml.nsmap).getchildren():
            tag = etree.QName(element.tag).localname
            if tag == "meta":
                new_smil.head.append(Meta.parse(element))

        for element in xml.find("body", xml.nsmap).getchildren():
            tag = etree.QName(element.tag).localname
            if tag == "seq":
                if len(new_smil.body) == 0:
                    new_smil.body = Seq.parse(element)
                else:
                    new_smil.body.append(Seq.parse(element))
            if tag == "video":
                new_smil.append(SMILMediaItem.parse(element))

        return new_smil


class Seq(SMILListBase):
    """Seq

    seq element, can contain media items, or nested seq or par elements
    """

    def element(self):
        """Return SMIL XML element"""
        el = etree.Element("seq", nsmap=NSMAP)
        for element in self:
            el.append(element.element())
        return el

    def check(self, value):
        if not isinstance(value, (Seq, SMILMediaItem, Par)):
            raise TypeError(f"{value} is not a valid child of a sequence")

    @staticmethod
    def parse(xml):
        """Parse and return new Seq"""
        if isinstance(xml, (str, bytes)):
            xml = etree.fromstring(xml)

        new_seq = Seq()

        for element in xml.getchildren():
            tag = etree.QName(element.tag).localname
            if tag == "seq":
                new_seq.append(Seq.parse(element))
            if tag == "par":
                new_seq.append(Par.parse(element))
            elif tag in ("video", "audio"):
                new_seq.append(SMILMediaItem.parse(element))

        return new_seq


class MediaClipping(object):
    """MediaClipping

    Base class which implements begin and end properties for clipping
    """

    @property
    def begin(self):
        return self._begin

    @begin.setter
    def begin(self, begin):
        if isinstance(begin, datetime) or begin is None:
            self._begin = begin
        else:
            try:
                self._begin = parse_datetime(begin)
            except Exception:
                raise TypeError("begin should be a datetime")

    @property
    def end(self):
        return self._end

    @end.setter
    def end(self, end):
        if isinstance(end, datetime) or end is None:
            self._end = end
        else:
            try:
                self._end = parse_datetime(end)
            except Exception:
                raise TypeError("end should be a datetime")


class Par(SMILListBase, MediaClipping):
    """Par

    seq element, can contain media items, or nested seq or par elements
    can have begin and end attributes for clipping
    """

    def __init__(self, *args, **kwargs):
        self._list = list()
        self.list = list()
        self.begin = None
        self.end = None
        if len(args) == 1 and isinstance(args[0], list):
            self.extend(args[0])
        elif (
            len(args) == 0
            and len(kwargs) == 1
            and "list" in kwargs
            and isinstance(kwargs["list"], list)
        ):
            self.extend(kwargs["list"])
        else:
            self.extend(list(args))

        if "begin" in kwargs:
            self.begin = kwargs["begin"]
        if "end" in kwargs:
            self.end = kwargs["end"]

    def element(self):
        """Return SMIL XML element"""
        el = etree.Element("par", nsmap=NSMAP)
        for element in self:
            el.append(element.element())
        if self.begin is not None:
            el.set(
                "clipBegin",
                f"wallclock({self.begin.isoformat().replace('+00:00', 'Z')})",
            )
        if self.end is not None:
            el.set(
                "clipEnd",
                f"wallclock({self.end.isoformat().replace('+00:00', 'Z')})",
            )
        return el

    def check(self, value):
        if not isinstance(value, (Seq, SMILMediaItem, Par)):
            raise TypeError(f"{value} is not a valid child of a par")

    @staticmethod
    def parse(xml):
        """Parse and return new Par"""
        if isinstance(xml, (str, bytes)):
            xml = etree.fromstring(xml)

        new_par = Par()

        if "clipBegin" in xml.attrib:
            new_par.begin = _stripwallclock(xml.attrib["clipBegin"])

        if "clipEnd" in xml.attrib:
            new_par.end = _stripwallclock(xml.attrib["clipEnd"])

        for element in xml.getchildren():
            tag = etree.QName(element.tag).localname
            if tag == "seq":
                new_par.append(Seq.parse(element))
            if tag == "par":
                new_par.append(Par.parse(element))
            elif tag in ("video", "audio"):
                new_par.append(SMILMediaItem.parse(element))

        return new_par


class SMILMediaItem(SMILBase, MediaClipping):
    """SMILMediaItem

    Media type item (video, audio, etc)
    Must have a src string, and optionally may have begin and end datetimes
    """

    def __init__(self, tag, src, begin=None, end=None):
        self.tag = tag
        self.src = src
        self.begin = begin
        self.end = end

    # properties
    @property
    def tag(self):
        return self._tag

    @tag.setter
    def tag(self, tag):
        if tag in ["audio", "video"]:
            self._tag = tag
        else:
            raise TypeError("tag must be audio or video")

    @property
    def src(self):
        return self._src

    @src.setter
    def src(self, src):
        if isinstance(src, str):
            self._src = src
        else:
            raise TypeError("src must be a string")

    def element(self):
        """Return SMIL XML element"""
        el = etree.Element(self.tag, nsmap=NSMAP)
        el.set("src", self.src)
        if self.begin is not None:
            el.set(
                "clipBegin",
                f"wallclock({self.begin.isoformat().replace('+00:00', 'Z')})",
            )
        if self.end is not None:
            el.set(
                "clipEnd",
                f"wallclock({self.end.isoformat().replace('+00:00', 'Z')})",
            )
        return el

    @staticmethod
    def parse(xml):
        """Parse and return new SMILMediaItem"""
        if isinstance(xml, (str, bytes)):
            xml = etree.fromstring(xml)

        tag = etree.QName(xml.tag).localname

        src = xml.attrib["src"]
        begin = None
        end = None

        if "clipBegin" in xml.attrib:
            begin = _stripwallclock(xml.attrib["clipBegin"])

        if "clipEnd" in xml.attrib:
            end = _stripwallclock(xml.attrib["clipEnd"])

        return SMILMediaItem(tag, src, begin, end)


class Video(SMILMediaItem):
    def __init__(self, src, begin=None, end=None):
        super().__init__("video", src, begin, end)


class Audio(SMILMediaItem):
    def __init__(self, src, begin=None, end=None):
        super().__init__("audio", src, begin, end)


class Sequence(SMILListBase):
    def element(self):
        seq = etree.Element("seq", nsmap=NSMAP)
        for i in self.list:
            seq.append(i.element())
        return seq


class Meta(SMILBase):
    def __init__(self, name, content):
        self.name = name
        self.content = content

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        if isinstance(name, str):
            self._name = name
        else:
            raise TypeError("name must be a string")

    @property
    def content(self):
        return self._content

    @content.setter
    def content(self, content):
        if isinstance(content, str):
            self._content = content
        else:
            raise TypeError("content must be a string")

    def element(self):
        meta = etree.Element("meta", nsmap=NSMAP)
        meta.set("name", self.name)
        meta.set("content", self.content)
        return meta

    @staticmethod
    def parse(xml):
        if isinstance(xml, (str, bytes)):
            xml = etree.fromstring(xml)

        return Meta(xml.attrib["name"], xml.attrib["content"])


class Head(SMILListBase):
    def element(self):
        """Return SMIL XML element"""
        el = etree.Element("head", nsmap=NSMAP)
        for element in self:
            el.append(element.element())
        return el

    def check(self, value):
        if not isinstance(value, (Meta)):
            raise TypeError(f"{value} is not a valid child of a sequence")

    @staticmethod
    def parse(xml):
        """Parse and return new Head"""
        if isinstance(xml, (str, bytes)):
            xml = etree.fromstring(xml)

        new_head = Head()

        for element in xml.getchildren():
            tag = etree.QName(element.tag).localname
            if tag == "meta":
                new_head.append(Meta.parse(element))

        return new_head


TAGMAP = {
    "smil": SMIL,
    "video": Video,
    "audio": Audio,
    "seq": Seq,
    "par": Par,
    "meta": Meta,
}
